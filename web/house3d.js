"use strict";

/**
 * Mô hình Ngôi Nhà Thông Minh 3D (Interactive 3D Smart Home Digital Twin)
 * Xây dựng bằng Three.js (WebGL) — Đồng bộ 100% hợp đồng phần cứng 6 thiết bị + 3 cảm biến:
 *  1. main_door         : Cửa chính + Servo SG90 (Chân D1 / GPIO5, 0° đóng / 90° mở)
 *  2. living_room_light : Đèn phòng khách (Chân D0 / GPIO16, LED 5mm + trở hạn dòng)
 *  3. bedroom_light     : Đèn phòng ngủ (Chân D4 / GPIO2, đấu nối an toàn khi boot)
 *  4. garden_pump       : Máy bơm chìm mini 5V trắng (Chân D6 / GPIO12 qua Relay 1 xanh + 1N4007 + tụ 470uF)
 *  5. alarm_siren       : Còi báo động Buzzer 5V (Chân D8 / GPIO15, active-HIGH, im lặng khi boot)
 *  6. speaker_amp       : Nguồn mạch loa PAM8403 xanh (Chân D7 / GPIO13 qua Relay 2 opto đỏ + PWM D3 / GPIO0)
 *                         kèm loa tròn bạc mini phát nhạc/âm báo
 *  7. DHT11             : Cảm biến Nhiệt độ & Độ ẩm màu xanh (Chân D2 / GPIO4)
 *  8. Soil Moisture     : Cảm biến độ ẩm đất 2 nhánh + mạch so sánh LM393 (Chân A0 / ADC0, <40% bật bơm, >=70% tắt)
 *  9. KY-037 Sound      : Cảm biến âm thanh PCB đỏ (Chân DO -> D5 / GPIO14) phát hiện vỗ tay / tiếng động lớn
 * 10. Trạm Mạch Trung Tâm: NodeMCU ESP8266 v2 Amica (0.9" 2x15) cắm trên Hub PCB 100x80mm 1-lớp DIY (Q1 S8050 + 7 jumper),
 *                         Relay 1 xanh, Relay 2 opto đỏ, PAM8403 xanh, loa tròn bạc, KY-037 đỏ, diode 1N4007 & tụ 470uF.
 */
window.SmartHome3D = (() => {
  let container, labelsContainer;
  let scene, camera, renderer;
  let onDeviceClickCallback = null;
  let isSoftwareRenderer = false;

  // Điều khiển góc nhìn Camera
  let camState = {
    theta: 0.44,
    phi: 1.02,
    radius: 14.8,
    targetX: 0.1,
    targetY: 1.0,
    targetZ: 0.6,
    autoRotate: false,
  };
  let camGoal = { ...camState };
  let isDragging = false;
  let prevMouse = { x: 0, y: 0 };
  let mouseDownPos = { x: 0, y: 0 };
  const clickableMeshes = [];
  const raycaster = new THREE.Raycaster();
  const mouseVec = new THREE.Vector2();

  // Cấu hình góc nhìn từ SCENE_SPEC.json (nếu nhánh CAD đã merge)
  const sceneSpecPresets = {};
  let sceneSpecLoaded = false;
  let activeVillaRoot = null;

  function setNodeName(obj, name) {
    if (obj && typeof obj !== "function") {
      try {
        obj.name = name;
      } catch (_) {}
    }
  }

  function registerClickable(obj, deviceId) {
    if (!obj) return;
    if (obj.isMesh) {
      obj.userData = obj.userData || {};
      obj.userData.deviceId = deviceId;
      if (!clickableMeshes.includes(obj)) {
        clickableMeshes.push(obj);
      }
    }
    if (obj.traverse) {
      obj.traverse((child) => {
        if (child.isMesh) {
          child.userData = child.userData || {};
          child.userData.deviceId = deviceId;
          if (!clickableMeshes.includes(child)) {
            clickableMeshes.push(child);
          }
        }
      });
    }
    obj.userData = obj.userData || {};
    obj.userData.deviceId = deviceId;
  }

  // Trạng thái 6 thiết bị chấp hành (Locked Contract)
  const deviceStates = {
    main_door: false,         // D1 (GPIO5): Servo SG90 (OPEN / CLOSED)
    living_room_light: false, // D0 (GPIO16): LED phòng khách (ON / OFF)
    bedroom_light: false,     // D4 (GPIO2): LED phòng ngủ (ON / OFF)
    garden_pump: false,       // D6 (GPIO12): Relay 1 xanh + Máy bơm 5V (ON / OFF)
    alarm_siren: false,       // D8 (GPIO15): Buzzer 5V (ON / OFF)
    speaker_amp: false,       // D7 (GPIO13) + D3 (GPIO0): Relay 2 opto đỏ + PAM8403 + Loa bạc (ON / OFF)
  };

  // Trạng thái 3 cảm biến thực tế (Locked Contract)
  const sensorState = {
    soil_moisture_pct: 62,
    soil_status: "Đủ ẩm",
    temp_c: 28.5,
    humidity_pct: 65,
    sound_detected: false,
    do_state: 0,
    event_count: 0,
    sound_status: "Yên tĩnh",
    wifi_rssi: -52,
  };

  // Các đối tượng 3D cần diễn hoạt (animate)
  let doorPivot = null;
  let servoHornPivot = null;
  let doorLockLedMat = null;
  let doorEntranceLight = null;
  let currentDoorAngle = 0;

  let livingBulbMat = null;
  let livingPointLight = null;
  let livingLedGlowGroup = null;

  let bedBulbMat = null;
  let bedLampShadeMat = null;
  let bedPointLight = null;
  let bedLedGlowGroup = null;

  let sirenBulbMat = null;
  let sirenPointLight = null;

  // Máy bơm tưới cây (D6) & Bồn cây sân vườn & Cảm biến đất (A0)
  let pumpBodyMat = null;
  let pumpImpeller = null;
  let pumpWaterParticles = null;
  let pumpPointLight = null;
  let gardenSoilMat = null;
  let lm393AlertLedMat = null;

  // Mạch loa PAM8403 (D7/D3) & Vòng sóng âm 3D
  let audioWaveRings = [];
  let audioWaveTimer = 0;
  let spkLedMat = null;
  let pamPowerLedMat = null;
  let speakerConeMesh = null;
  let speakerDiaphragmMat = null;

  // Cảm biến âm thanh KY-037 (D5 DO)
  let ky037WaveRing = null;
  let ky037WaveMat = null;
  let ky037PulseTimer = 0;
  let lastSoundEventCount = 0;

  // Tay nắm fallback để ẩn khi GLB có node khóa tương ứng
  const fallbackHandles = {};
  const glbHandles = {
    doorPivot: null,
    servoHornPivot: null,
    livingLedNode: null,
    bedLedNode: null,
    servoMats: [],
    psuMats: [],
    lm393Mats: [],
    livingMats: [],
    bedMats: [],
    pumpMats: [],
    relay1Mats: [],
    relay2Mats: [],
    buzzerMats: [],
    speakerMeshes: [],
    speakerMats: [],
    pamMats: [],
    ky037Mats: [],
    pinBindings: [],
    boundNodes: [],
  };

  // Hệ thống Đường Dây Điện 3D nối từ PCB Hub DIY v3 (40 dây thực tế từ wiring_contract.json — KHÔNG Breadboard)
  let wireConduitGroup = null;
  let contractWiresGroup = null;
  let onWireClickCallback = null;
  const wireConduitMeshes = {};
  const glbWireEntries = [];
  const contractWireEntries = [];
  const contractWireMetaById = {};
  let contractWiresLoaded = false;
  const wiringDisplayState = {
    visible: true,
    selectedModuleId: "all",
    allowedKeys: null,
    activeWire: null,
  };
  const wireMats = {
    d1_door: null,
    d0_living: null,
    d4_bedroom: null,
    d6_pump: null,
    d8_siren: null,
    d7_d3_speaker: null,
    d2_dht11: null,
    a0_soil: null,
    d5_ky037: null,
  };

  // Đèn LED báo trạng thái trực tiếp trên Bảng mạch 3D
  const boardLedMats = {
    esp_onboard: null,
    d0_living: null,
    d4_bedroom: null,
    d6_relay_blue: null,
    d7_relay_red: null,
    d8_buzzer: null,
    d7_pam8403_pwr: null,
    d5_ky037_do: null,
  };

  // Điểm neo 3D để gắn nhãn nổi HTML (Floating 3D Pins)
  const pinAnchors = {};
  const pinElements = {};
  let currentCameraPreset = "overview";
  let labelsUserOverride = null; // null = tự động ẩn trên mobile & góc nhìn Mạch ESP
  let labelsVisible = true;

  // 17 Nhãn 3D đồng bộ SSOT: 6 thiết bị chấp hành + đủ 14 mô-đun ngoại vi + NodeMCU v2 Amica + PCB Hub DIY v3
  const PIN_META = [
    { id: "main_door", moduleId: "main_door", kind: "device", icon: "", shortName: "Cửa chính (D1)", pos: [-2.95, 1.65, 3.95] },
    { id: "living_room_light", moduleId: "led_living", kind: "device", icon: "", shortName: "LED khách (D0·J4)", pos: [-0.11, 3.35, 0.08] },
    { id: "bedroom_light", moduleId: "led_bedroom", kind: "device", icon: "", shortName: "LED ngủ (D4·J5)", pos: [-0.04, 3.35, -0.58] },
    { id: "garden_pump", moduleId: "pump_unit", kind: "device", icon: "", shortName: "Bơm vườn (D6·J2)", pos: [2.23, 0.78, 3.65] },
    { id: "alarm_siren", moduleId: "buzzer_alarm", kind: "device", icon: "", shortName: "Còi 5V (D8·J6)", pos: [-0.08, 3.38, 1.0] },
    { id: "speaker_amp", moduleId: "pam8403_amp", kind: "device", icon: "", shortName: "PAM8403 (J11/J12)", pos: [0.53, 0.45, 4.58] },
    { id: "sensor_soil_a0", moduleId: "soil_probe", kind: "sensor", cam: "garden", icon: "", shortName: "Đầu dò YL-69 (A0)", pos: [3.88, 1.1, 3.65] },
    { id: "sensor_dht11_d2", moduleId: "dht11_sensor", kind: "sensor", cam: "living", icon: "", shortName: "DHT11 (D2·J13)", pos: [-0.11, 2.55, -1.28] },
    { id: "sensor_ky037_d5", moduleId: "ky037_sound", kind: "sensor", cam: "board", icon: "", shortName: "KY-037 (D5·J15)", pos: [-0.88, 0.92, 1.0] },
    { id: "board_esp8266", moduleId: "nodemcu", kind: "sensor", cam: "board", icon: "", shortName: "NodeMCU v2", pos: [-2.06, 1.08, 3.24] },
    { id: "mod_hub_pcb", moduleId: "hub_pcb", kind: "module", cam: "board", icon: "", shortName: "PCB Hub v3 (J1→ra)", defaultBadge: "15 cổng", pos: [-2.03, 0.72, 3.28] },
    { id: "mod_sg90_servo", moduleId: "sg90_servo", kind: "module", cam: "door", icon: "", shortName: "Servo SG90 (D1·J3)", defaultBadge: "0° ĐÓNG", pos: [-3.29, 3.18, 0.84] },
    { id: "mod_psu_5v", moduleId: "psu_5v", kind: "module", cam: "board", icon: "", shortName: "Nguồn 5V DC-022→J1", defaultBadge: "5V 2A", pos: [-4.25, 0.75, 5.45] },
    { id: "mod_soil_lm393", moduleId: "soil_lm393", kind: "module", cam: "garden", icon: "", shortName: "LM393 Đất (A0·J14)", defaultBadge: "3.3V", pos: [2.85, 0.65, 1.55] },
    { id: "mod_relay1_pump", moduleId: "relay1_pump", kind: "module", cam: "board", icon: "", shortName: "Rơ-le 1 Bơm (D6)", defaultBadge: "TẮT", pos: [0.58, 0.55, 2.48] },
    { id: "mod_relay2_speaker", moduleId: "relay2_speaker", kind: "module", cam: "board", icon: "", shortName: "Rơ-le 2 Loa (D7)", defaultBadge: "TẮT", pos: [0.58, 0.55, 3.58] },
    { id: "mod_speaker_mini", moduleId: "speaker_mini", kind: "module", cam: "board", icon: "", shortName: "Loa mini 28mm", defaultBadge: "8Ω BTL", pos: [0.5, 0.92, 5.49] },
  ];

  function resetGlbHandles() {
    glbHandles.doorPivot = null;
    glbHandles.servoHornPivot = null;
    glbHandles.livingLedNode = null;
    glbHandles.bedLedNode = null;
    glbHandles.servoMats = [];
    glbHandles.psuMats = [];
    glbHandles.lm393Mats = [];
    glbHandles.livingMats = [];
    glbHandles.bedMats = [];
    glbHandles.pumpMats = [];
    glbHandles.relay1Mats = [];
    glbHandles.relay2Mats = [];
    glbHandles.buzzerMats = [];
    glbHandles.speakerMeshes = [];
    glbHandles.speakerMats = [];
    glbHandles.pamMats = [];
    glbHandles.ky037Mats = [];
    glbHandles.pinBindings = [];
    glbHandles.boundNodes = [];
    glbWireEntries.length = 0;
    contractWireEntries.length = 0;
    Object.keys(contractWireMetaById).forEach((k) => delete contractWireMetaById[k]);
    contractWiresLoaded = false;
    contractWiresGroup = null;
  }

  function inferGlbWireMeta(nodeName) {
    const n = String(nodeName || "");
    if (/J3_SERVO/i.test(n)) return { moduleId: "sg90_servo", hubRef: "J3", wireKey: "d1_door", defaultWireId: "W03" };
    if (/J4_LR_LED/i.test(n)) return { moduleId: "led_living", hubRef: "J4", wireKey: "d0_living", defaultWireId: "W06" };
    if (/J5_BR_LED/i.test(n)) return { moduleId: "led_bedroom", hubRef: "J5", wireKey: "d4_bedroom", defaultWireId: "W08" };
    if (/J13_DHT11/i.test(n)) return { moduleId: "dht11_sensor", hubRef: "J13", wireKey: "d2_dht11", defaultWireId: "W31" };
    if (/J15_KY037/i.test(n)) return { moduleId: "ky037_sound", hubRef: "J15", wireKey: "d5_ky037", defaultWireId: "W40" };
    if (/J6_BUZZ/i.test(n)) return { moduleId: "buzzer_alarm", hubRef: "J6", wireKey: "d8_siren", defaultWireId: "W18" };
    if (/J7_RLY1/i.test(n)) return { moduleId: "relay1_pump", hubRef: "J7", wireKey: "d6_pump", defaultWireId: "W12" };
    if (/J8_RLY1/i.test(n)) return { moduleId: "relay1_pump", hubRef: "J8", wireKey: "d6_pump", defaultWireId: "W13" };
    if (/J2_PUMP/i.test(n)) return { moduleId: "pump_unit", hubRef: "J2", wireKey: "d6_pump", defaultWireId: "W15" };
    if (/J9_RLY2/i.test(n)) return { moduleId: "relay2_speaker", hubRef: "J9", wireKey: "d7_d3_speaker", defaultWireId: "W21" };
    if (/J10_RLY2/i.test(n)) return { moduleId: "relay2_speaker", hubRef: "J10", wireKey: "d7_d3_speaker", defaultWireId: "W22" };
    if (/J11_AMP_PWR/i.test(n)) return { moduleId: "pam8403_amp", hubRef: "J11", wireKey: "d7_d3_speaker", defaultWireId: "W24" };
    if (/J12_AUDIO/i.test(n)) return { moduleId: "pam8403_amp", hubRef: "J12", wireKey: "d7_d3_speaker", defaultWireId: "W26" };
    if (/PAM_Spk_Pos/i.test(n)) return { moduleId: "speaker_mini", hubRef: "PAM8403", wireKey: "d7_d3_speaker", defaultWireId: "W28" };
    if (/PAM_Spk_Neg/i.test(n)) return { moduleId: "speaker_mini", hubRef: "PAM8403", wireKey: "d7_d3_speaker", defaultWireId: "W29" };
    if (/J14_SOIL/i.test(n)) return { moduleId: "soil_lm393", hubRef: "J14", wireKey: "a0_soil", defaultWireId: "W35" };
    if (/J1_PWR/i.test(n)) return { moduleId: "psu_5v", hubRef: "J1", wireKey: "power", defaultWireId: "W01" };
    return null;
  }

  function parseHexColorInt(hexStr, fallbackHex = 0x38bdf8) {
    if (typeof hexStr === "number" && Number.isFinite(hexStr)) return hexStr;
    const clean = String(hexStr || "").trim().replace(/^#/, "");
    if (/^[0-9a-fA-F]{6}$/.test(clean)) {
      return parseInt(clean, 16);
    }
    return fallbackHex;
  }

  function buildContractWires3D(contract) {
    if (!scene || !window.THREE || !contract || !Array.isArray(contract.wires)) return 0;
    if (contractWiresGroup && scene.remove) {
      scene.remove(contractWiresGroup);
    }
    contractWireEntries.length = 0;
    Object.keys(contractWireMetaById).forEach((k) => delete contractWireMetaById[k]);

    contractWiresGroup = new THREE.Group();
    contractWiresGroup.name = "pcb_direct_40_wires";

    contract.wires.forEach((w) => {
      if (!w || !w.wire_id) return;
      contractWireMetaById[w.wire_id] = w;
      const pts = Array.isArray(w.waypoints_threejs) ? w.waypoints_threejs : [];
      if (pts.length < 2) return;

      const vecs = [];
      for (let i = 0; i < pts.length; i++) {
        const p = pts[i];
        if (!Array.isArray(p) || p.length < 3) continue;
        const vx = Number(p[0]);
        const vy = Number(p[1]);
        const vz = Number(p[2]);
        if (!Number.isFinite(vx) || !Number.isFinite(vy) || !Number.isFinite(vz)) continue;
        if (vecs.length > 0) {
          const prev = vecs[vecs.length - 1];
          if (Math.hypot(vx - prev.x, vy - prev.y, vz - prev.z) < 1e-4) continue;
        }
        vecs.push(new THREE.Vector3(vx, vy, vz));
      }
      if (vecs.length < 2) return;

      const colorHex = parseHexColorInt(w.color_hex, 0x38bdf8);
      const isDarkBlack = colorHex === 0x18181b || String(w.color || "").toLowerCase() === "black";
      const displayColor = isDarkBlack ? 0x27272a : colorHex;
      const baseEmissive = isDarkBlack ? 0x0f172a : colorHex;
      const radius = w.wire_type && /22AWG/i.test(w.wire_type) ? 0.017 : 0.0135;

      let wireObj = null;
      let mat = null;
      if (typeof THREE.CatmullRomCurve3 === "function" && typeof THREE.TubeGeometry === "function") {
        const curve = new THREE.CatmullRomCurve3(vecs, false, "catmullrom", 0.06);
        const tubularSegments = Math.max(18, Math.min(72, vecs.length * 5));
        const geo = new THREE.TubeGeometry(curve, tubularSegments, radius, 6, false);
        mat = new THREE.MeshStandardMaterial({
          color: displayColor,
          emissive: baseEmissive,
          emissiveIntensity: isDarkBlack ? 0.12 : 0.22,
          roughness: 0.38,
          metalness: 0.12,
        });
        wireObj = new THREE.Mesh(geo, mat);
        wireObj.castShadow = false;
      } else if (typeof THREE.BufferGeometry === "function" && typeof THREE.Line === "function") {
        const geo = new THREE.BufferGeometry().setFromPoints(vecs);
        mat = new THREE.LineBasicMaterial({ color: displayColor });
        wireObj = new THREE.Line(geo, mat);
      }
      if (!wireObj) return;

      wireObj.name = `ContractWire_${w.wire_id}`;
      wireObj.userData = {
        wireId: w.wire_id,
        moduleId: w.module_id,
        hubRef: w.hub_ref,
        wireKey: w.house3d_wire_key || "power",
        lengthCm: typeof w.length_cm === "number" ? w.length_cm : null,
        recommendedStdCm: w.recommended_std_cm || null,
        routeChannel: w.route_channel || "",
      };
      clickableMeshes.push(wireObj);
      contractWiresGroup.add(wireObj);

      contractWireEntries.push({
        wireId: w.wire_id,
        moduleId: w.module_id,
        hubRef: w.hub_ref,
        wireKey: w.house3d_wire_key || "power",
        lengthCm: typeof w.length_cm === "number" ? w.length_cm : null,
        recommendedStdCm: w.recommended_std_cm || null,
        routeChannel: w.route_channel || "",
        colorHex: displayColor,
        baseEmissive,
        isDarkBlack,
        mesh: wireObj,
        mat,
      });
    });

    if (contractWireEntries.length > 0) {
      contractWiresLoaded = true;
      scene.add(contractWiresGroup);
      applyWiringDisplayState();
    }
    return contractWireEntries.length;
  }

  function loadWiringContract3D() {
    if (typeof fetch !== "function") {
      return Promise.resolve(null);
    }
    const urls = ["/static/data/wiring_contract.json", "/data/wiring_contract.json"];
    const tryUrl = (idx) => {
      if (idx >= urls.length) return Promise.resolve(null);
      return fetch(urls[idx], { cache: "no-cache" })
        .then((res) => {
          if (!res || !res.ok) return tryUrl(idx + 1);
          return res.json().catch(() => tryUrl(idx + 1));
        })
        .then((data) => {
          if (data && Array.isArray(data.wires) && data.wires.length > 0) {
            buildContractWires3D(data);
            return data;
          }
          return tryUrl(idx + 1);
        })
        .catch(() => tryUrl(idx + 1));
    };
    try {
      return tryUrl(0);
    } catch (_) {
      return Promise.resolve(null);
    }
  }

  function applyWiringDisplayState() {
    const visible = Boolean(wiringDisplayState.visible);
    const selMod = wiringDisplayState.selectedModuleId || "all";
    const allowedKeys = wiringDisplayState.allowedKeys;
    const active = wiringDisplayState.activeWire;
    const hasContractWires = contractWiresLoaded && contractWireEntries.length > 0;

    if (contractWiresGroup) {
      contractWiresGroup.visible = visible && hasContractWires;
    }

    if (hasContractWires) {
      contractWireEntries.forEach((entry) => {
        if (!entry || !entry.mesh) return;
        const inFilter =
          selMod === "all" ||
          entry.moduleId === selMod ||
          (allowedKeys && allowedKeys.has(entry.wireKey));
        entry.mesh.visible = visible && inFilter;

        const m = entry.mat;
        if (!m) return;
        if (!active) {
          m.transparent = false;
          m.opacity = 1.0;
          if (m.emissive && typeof m.emissive.setHex === "function") {
            m.emissive.setHex(entry.baseEmissive);
          }
          if (m.emissiveIntensity !== undefined) {
            m.emissiveIntensity = entry.isDarkBlack ? 0.12 : 0.22;
          }
        } else {
          const isMatch = entry.wireId === active.wire_id;
          m.transparent = !isMatch;
          m.opacity = isMatch ? 1.0 : 0.12;
          if (m.emissive && typeof m.emissive.setHex === "function") {
            m.emissive.setHex(isMatch ? 0x38bdf8 : entry.baseEmissive);
          }
          if (m.emissiveIntensity !== undefined) {
            m.emissiveIntensity = isMatch ? 1.65 : 0.02;
          }
        }
        m.needsUpdate = true;
      });
    }

    if (wireConduitGroup) {
      wireConduitGroup.visible = visible && !hasContractWires;
    }

    Object.entries(wireConduitMeshes).forEach(([key, mesh]) => {
      if (!mesh) return;
      const inFilter =
        selMod === "all" ||
        !allowedKeys ||
        allowedKeys.has(key);
      mesh.visible = visible && !hasContractWires && inFilter;
      const mat = wireMats[key];
      if (!mat) return;
      if (!active) {
        mat.transparent = false;
        mat.opacity = 1.0;
        mat.emissiveIntensity = 0.28;
      } else {
        const isMatch = active.house3d_wire_key === key;
        mat.transparent = !isMatch;
        mat.opacity = isMatch ? 1.0 : 0.14;
        mat.emissiveIntensity = isMatch ? 2.1 : 0.05;
      }
      mat.needsUpdate = true;
    });

    glbWireEntries.forEach((entry) => {
      if (!entry || !entry.mesh) return;
      const isGlbWireCurve = /^Wire_/i.test(String(entry.mesh.name || ""));
      if (hasContractWires && isGlbWireCurve) {
        entry.mesh.visible = false;
        return;
      }
      const inFilter =
        selMod === "all" ||
        entry.moduleId === selMod ||
        (selMod === "soil_probe" && entry.moduleId === "soil_lm393") ||
        (allowedKeys && allowedKeys.has(entry.wireKey));
      entry.mesh.visible = visible && inFilter;

      const isMatch = Boolean(
        active &&
          (entry.hubRef === active.hub_ref ||
            entry.moduleId === active.module_id ||
            (active.module_id === "soil_probe" && entry.moduleId === "soil_lm393"))
      );
      (entry.materials || []).forEach((m) => {
        if (!m) return;
        if (!active) {
          m.transparent = false;
          m.opacity = 1.0;
          if (m.emissive && typeof m.emissive.setHex === "function") m.emissive.setHex(0x000000);
          if (m.emissiveIntensity !== undefined) m.emissiveIntensity = 0;
        } else if (isMatch) {
          m.transparent = false;
          m.opacity = 1.0;
          if (m.emissive && typeof m.emissive.setHex === "function") m.emissive.setHex(0x38bdf8);
          if (m.emissiveIntensity !== undefined) m.emissiveIntensity = 1.35;
        } else {
          m.transparent = true;
          m.opacity = 0.14;
          if (m.emissive && typeof m.emissive.setHex === "function") m.emissive.setHex(0x000000);
          if (m.emissiveIntensity !== undefined) m.emissiveIntensity = 0;
        }
        m.needsUpdate = true;
      });
    });
  }

  function init(canvasContainerId, overlayLabelsId, onToggleDevice) {
    container = document.getElementById(canvasContainerId);
    labelsContainer = document.getElementById(overlayLabelsId);
    onDeviceClickCallback = onToggleDevice;
    if (!container || !window.THREE) return;

    resetGlbHandles();
    activeVillaRoot = null;
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b1324);
    scene.fog = new THREE.FogExp2(0x0b1324, 0.015);

    const w = container.clientWidth || 800;
    const h = container.clientHeight || 520;
    camera = new THREE.PerspectiveCamera(40, w / h, 0.1, 100);

    renderer = new THREE.WebGLRenderer({
      antialias: true,
      powerPreference: "high-performance",
      preserveDrawingBuffer: true,
    });
    renderer.setSize(w, h);
    let isSoftwareGl = Boolean(
      typeof navigator !== "undefined" &&
        (Boolean(navigator.webdriver) || /HeadlessChrome/i.test(String(navigator.userAgent || "")))
    );
    if (!isSoftwareGl && renderer && typeof renderer.getContext === "function") {
      try {
        const gl = renderer.getContext();
        const dbg = gl && gl.getExtension ? gl.getExtension("WEBGL_debug_renderer_info") : null;
        if (dbg) {
          const glRendererStr = String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) || "");
          if (/SwiftShader|llvmpipe|Software/i.test(glRendererStr)) {
            isSoftwareGl = true;
          }
        }
      } catch (_) {}
    }
    isSoftwareRenderer = isSoftwareGl;
    renderer.setPixelRatio(isSoftwareGl ? 1 : Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = !isSoftwareGl;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    if (THREE.ACESFilmicToneMapping !== undefined) {
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.18;
    }
    if (THREE.sRGBEncoding !== undefined) {
      renderer.outputEncoding = THREE.sRGBEncoding;
    }
    clickableMeshes.length = 0;
    const existingCanvas = container.querySelector("canvas");
    if (existingCanvas) {
      existingCanvas.remove();
    }
    container.insertBefore(renderer.domElement, container.firstChild);

    currentCameraPreset = "overview";
    labelsUserOverride = null;
    lastRenderTimeMs = 0;
    renderedFramesCount = 0;
    buildLighting();
    buildGroundAndLoadBlenderVilla();
    buildSmartDevices();
    buildHardwareKit3D();
    loadWiringContract3D();
    buildFloatingPins();
    syncLabelsVisibilityUi();
    bindMouseControls();

    window.addEventListener("resize", onResize);
    requestAnimationFrame(animate);
  }

  function buildLighting() {
    const hemi = new THREE.HemisphereLight(0xdbeafe, 0x1e293b, 0.72);
    scene.add(hemi);

    const sunDir = new THREE.DirectionalLight(0xfffbeb, 0.92);
    sunDir.position.set(9, 16, 12);
    sunDir.castShadow = true;
    sunDir.shadow.mapSize.width = 2048;
    sunDir.shadow.mapSize.height = 2048;
    sunDir.shadow.camera.near = 1;
    sunDir.shadow.camera.far = 40;
    sunDir.shadow.camera.left = -10;
    sunDir.shadow.camera.right = 10;
    sunDir.shadow.camera.top = 10;
    sunDir.shadow.camera.bottom = -10;
    sunDir.shadow.bias = -0.0005;
    scene.add(sunDir);

    const fillDir = new THREE.DirectionalLight(0x93c5fd, 0.35);
    fillDir.position.set(-10, 8, -8);
    scene.add(fillDir);
  }

  function cloneNodeMaterials(obj) {
    const mats = [];
    if (!obj) return mats;
    const collect = (node) => {
      if (node && node.isMesh && node.material) {
        if (Array.isArray(node.material)) {
          node.material = node.material.map((m) => (m && typeof m.clone === "function" ? m.clone() : m));
          node.material.forEach((m) => { if (m) mats.push(m); });
        } else {
          if (typeof node.material.clone === "function") {
            node.material = node.material.clone();
          }
          mats.push(node.material);
        }
      }
    };
    if (typeof obj.traverse === "function") {
      obj.traverse(collect);
    } else {
      collect(obj);
    }
    return mats;
  }

  function isFiniteVec3(v) {
    return Boolean(
      v &&
        typeof v.x === "number" &&
        Number.isFinite(v.x) &&
        typeof v.y === "number" &&
        Number.isFinite(v.y) &&
        typeof v.z === "number" &&
        Number.isFinite(v.z)
    );
  }

  function isValidBox3(b) {
    if (!b || !isFiniteVec3(b.min) || !isFiniteVec3(b.max)) return false;
    if (typeof b.isEmpty === "function" && b.isEmpty() === true) return false;
    return (
      b.max.x >= b.min.x &&
      b.max.y >= b.min.y &&
      b.max.z >= b.min.z &&
      (b.max.x > b.min.x || b.max.y > b.min.y || b.max.z > b.min.z)
    );
  }

  function getPcbHubBounds() {
    if (!activeVillaRoot || typeof activeVillaRoot.getObjectByName !== "function") return null;
    if (typeof THREE.Box3 !== "function") return null;
    try {
      if (typeof activeVillaRoot.updateMatrixWorld === "function") {
        activeVillaRoot.updateMatrixWorld(true);
      }
      const kicadHub = activeVillaRoot.getObjectByName("kicad_pcb_hub") || null;
      const nodemcu = activeVillaRoot.getObjectByName("nodemcu_esp8266") || null;
      const targets = [];
      const nodeNames = [];
      if (kicadHub) {
        targets.push(kicadHub);
        nodeNames.push("kicad_pcb_hub");
      }
      if (nodemcu) {
        targets.push(nodemcu);
        nodeNames.push("nodemcu_esp8266");
      }
      if (!targets.length) return null;

      const box = new THREE.Box3();
      let hasAny = false;
      targets.forEach((node) => {
        const nodeBox = new THREE.Box3();
        if (typeof nodeBox.setFromObject !== "function") return;
        nodeBox.setFromObject(node);
        if (!isValidBox3(nodeBox)) return;
        if (!hasAny) {
          if (typeof box.copy === "function") {
            box.copy(nodeBox);
          } else {
            box.min = { x: nodeBox.min.x, y: nodeBox.min.y, z: nodeBox.min.z };
            box.max = { x: nodeBox.max.x, y: nodeBox.max.y, z: nodeBox.max.z };
          }
          hasAny = true;
        } else if (typeof box.union === "function") {
          box.union(nodeBox);
        } else {
          box.min.x = Math.min(box.min.x, nodeBox.min.x);
          box.min.y = Math.min(box.min.y, nodeBox.min.y);
          box.min.z = Math.min(box.min.z, nodeBox.min.z);
          box.max.x = Math.max(box.max.x, nodeBox.max.x);
          box.max.y = Math.max(box.max.y, nodeBox.max.y);
          box.max.z = Math.max(box.max.z, nodeBox.max.z);
        }
      });
      if (!hasAny || !isValidBox3(box)) return null;

      const center = {
        x: (box.min.x + box.max.x) * 0.5,
        y: (box.min.y + box.max.y) * 0.5,
        z: (box.min.z + box.max.z) * 0.5,
      };
      const size = {
        x: box.max.x - box.min.x,
        y: box.max.y - box.min.y,
        z: box.max.z - box.min.z,
      };
      if (!isFiniteVec3(center) || !isFiniteVec3(size)) return null;
      return { box, center, size, nodeNames };
    } catch (_) {
      return null;
    }
  }

  function computeBoardPresetFromBounds() {
    const bounds = getPcbHubBounds();
    if (!bounds) return null;

    const w = container && Number(container.clientWidth) > 0 ? Number(container.clientWidth) : 0;
    const h = container && Number(container.clientHeight) > 0 ? Number(container.clientHeight) : 0;
    const aspect =
      w > 0 && h > 0
        ? w / h
        : camera && typeof camera.aspect === "number" && Number.isFinite(camera.aspect) && camera.aspect > 0
          ? camera.aspect
          : 800 / 520;
    const fovDeg =
      camera && typeof camera.fov === "number" && Number.isFinite(camera.fov) && camera.fov > 1 && camera.fov < 175
        ? camera.fov
        : 40;

    const theta = -0.10;
    const phi = 0.78;
    const targetWidthFill = 0.72;
    const maxHeightFill = 0.91;

    const sinPhi = Math.sin(phi);
    const cosPhi = Math.cos(phi);
    const sinTheta = Math.sin(theta);
    const cosTheta = Math.cos(theta);

    const toEyeX = sinPhi * sinTheta;
    const toEyeY = cosPhi;
    const toEyeZ = sinPhi * cosTheta;

    const fwdX = -toEyeX;
    const fwdY = -toEyeY;
    const fwdZ = -toEyeZ;

    // right = normalize(forward x (0, 1, 0))
    const rawRx = -fwdZ;
    const rawRz = fwdX;
    const rLen = Math.hypot(rawRx, rawRz) || 1;
    const rightX = rawRx / rLen;
    const rightY = 0;
    const rightZ = rawRz / rLen;

    // up = right x forward
    const upX = rightY * fwdZ - rightZ * fwdY;
    const upY = rightZ * fwdX - rightX * fwdZ;
    const upZ = rightX * fwdY - rightY * fwdX;

    const tanHalfY = Math.tan((fovDeg * Math.PI) / 360);
    const tanHalfX = tanHalfY * aspect;
    if (!Number.isFinite(tanHalfY) || tanHalfY <= 0 || !Number.isFinite(tanHalfX) || tanHalfX <= 0) {
      return null;
    }

    const { min, max } = bounds.box;
    const { center } = bounds;
    let maxRW = 0;
    let maxRH = 0;
    for (const cx of [min.x, max.x]) {
      for (const cy of [min.y, max.y]) {
        for (const cz of [min.z, max.z]) {
          const dx = cx - center.x;
          const dy = cy - center.y;
          const dz = cz - center.z;
          const px = Math.abs(dx * rightX + dy * rightY + dz * rightZ);
          const py = Math.abs(dx * upX + dy * upY + dz * upZ);
          const pz = dx * toEyeX + dy * toEyeY + dz * toEyeZ;
          const rW = pz + px / (targetWidthFill * tanHalfX);
          const rH = pz + py / (maxHeightFill * tanHalfY);
          if (rW > maxRW) maxRW = rW;
          if (rH > maxRH) maxRH = rH;
        }
      }
    }

    const rawRadius = Math.max(maxRW, maxRH);
    if (!Number.isFinite(rawRadius) || rawRadius <= 0) return null;
    const radius = Math.max(1.5, Math.min(10.0, rawRadius));

    return {
      theta,
      phi,
      radius,
      targetX: center.x,
      targetY: center.y,
      targetZ: center.z,
    };
  }

  function refreshBoardCameraIfActive() {
    if (currentCameraPreset !== "board") return;
    const dynamicBoardCam = computeBoardPresetFromBounds();
    if (dynamicBoardCam) {
      Object.assign(camGoal, dynamicBoardCam);
    }
  }

  function getBoardFrameMetrics() {
    const bounds = getPcbHubBounds();
    const w = container && Number(container.clientWidth) > 0 ? Number(container.clientWidth) : 0;
    const h = container && Number(container.clientHeight) > 0 ? Number(container.clientHeight) : 0;
    const aspect =
      w > 0 && h > 0
        ? w / h
        : camera && typeof camera.aspect === "number" && Number.isFinite(camera.aspect)
          ? camera.aspect
          : null;

    let projected = null;
    if (bounds && camera && typeof THREE.Vector3 === "function") {
      try {
        if (typeof camera.updateMatrixWorld === "function") {
          camera.updateMatrixWorld(true);
        }
        const { min, max } = bounds.box;
        let minX = Infinity;
        let maxX = -Infinity;
        let minY = Infinity;
        let maxY = -Infinity;
        let valid = true;
        for (const cx of [min.x, max.x]) {
          for (const cy of [min.y, max.y]) {
            for (const cz of [min.z, max.z]) {
              const v = new THREE.Vector3(cx, cy, cz);
              if (typeof v.project !== "function") {
                valid = false;
                break;
              }
              v.project(camera);
              if (!isFiniteVec3(v)) {
                valid = false;
                break;
              }
              if (v.x < minX) minX = v.x;
              if (v.x > maxX) maxX = v.x;
              if (v.y < minY) minY = v.y;
              if (v.y > maxY) maxY = v.y;
            }
            if (!valid) break;
          }
          if (!valid) break;
        }
        if (valid && Number.isFinite(minX) && Number.isFinite(maxX) && Number.isFinite(minY) && Number.isFinite(maxY)) {
          projected = {
            widthRatio: (maxX - minX) * 0.5,
            heightRatio: (maxY - minY) * 0.5,
            minX,
            maxX,
            minY,
            maxY,
          };
        }
      } catch (_) {}
    }

    return {
      preset: currentCameraPreset,
      camState: { ...camState },
      camGoal: { ...camGoal },
      aspect,
      pcbBox: bounds
        ? {
            min: [bounds.box.min.x, bounds.box.min.y, bounds.box.min.z],
            max: [bounds.box.max.x, bounds.box.max.y, bounds.box.max.z],
            center: [bounds.center.x, bounds.center.y, bounds.center.z],
            size: [bounds.size.x, bounds.size.y, bounds.size.z],
            nodeNames: bounds.nodeNames.slice(),
          }
        : null,
      projected,
    };
  }

  function getNodeWorldCenter(obj) {
    if (!obj) return null;
    try {
      if (typeof THREE.Box3 === "function") {
        const box = new THREE.Box3();
        if (typeof box.setFromObject === "function" && typeof box.getCenter === "function") {
          box.setFromObject(obj);
          const c = new THREE.Vector3();
          box.getCenter(c);
          if (Number.isFinite(c.x) && Number.isFinite(c.y) && Number.isFinite(c.z)) {
            return c;
          }
        }
      }
      if (typeof obj.getWorldPosition === "function") {
        const wp = new THREE.Vector3();
        obj.getWorldPosition(wp);
        if (Number.isFinite(wp.x) && Number.isFinite(wp.y) && Number.isFinite(wp.z)) {
          return wp;
        }
      }
    } catch (_) {}
    return null;
  }

  function updatePinAnchorFromNode(pinId, obj, yOffset = 0.22) {
    const center = getNodeWorldCenter(obj);
    if (center && pinAnchors[pinId]) {
      pinAnchors[pinId].x = center.x;
      pinAnchors[pinId].y = center.y + yOffset;
      pinAnchors[pinId].z = center.z;
    }
  }

  function bindPinAnchor(pinId, obj, yOffset = 0.22) {
    if (!obj) return;
    glbHandles.pinBindings.push({ pinId, obj, yOffset });
    updatePinAnchorFromNode(pinId, obj, yOffset);
  }

  function repositionLedGlowAnchors() {
    if (glbHandles.livingLedNode) {
      const c = getNodeWorldCenter(glbHandles.livingLedNode);
      if (c) {
        if (livingLedGlowGroup && livingLedGlowGroup.position && typeof livingLedGlowGroup.position.set === "function") {
          livingLedGlowGroup.position.set(c.x - 0.06, c.y, c.z);
        }
        if (livingPointLight && livingPointLight.position && typeof livingPointLight.position.set === "function") {
          livingPointLight.position.set(c.x - 0.55, c.y - 0.25, c.z);
        }
      }
    }
    if (glbHandles.bedLedNode) {
      const c = getNodeWorldCenter(glbHandles.bedLedNode);
      if (c) {
        if (bedLedGlowGroup && bedLedGlowGroup.position && typeof bedLedGlowGroup.position.set === "function") {
          bedLedGlowGroup.position.set(c.x + 0.06, c.y, c.z);
        }
        if (bedPointLight && bedPointLight.position && typeof bedPointLight.position.set === "function") {
          bedPointLight.position.set(c.x + 0.55, c.y - 0.25, c.z);
        }
      }
    }
  }

  function recomputeBoundPinAnchors() {
    if (glbHandles.pinBindings && glbHandles.pinBindings.length) {
      glbHandles.pinBindings.forEach((b) => {
        if (b && b.obj) {
          updatePinAnchorFromNode(b.pinId, b.obj, b.yOffset);
        }
      });
    }
    repositionLedGlowAnchors();
  }

  function parsePresetObj(raw) {
    if (!raw || typeof raw !== "object") return null;
    const out = {};
    const tgt = Array.isArray(raw.target) && raw.target.length >= 3
      ? { x: Number(raw.target[0]), y: Number(raw.target[1]), z: Number(raw.target[2]) }
      : (raw.target && typeof raw.target === "object"
        ? { x: Number(raw.target.x), y: Number(raw.target.y), z: Number(raw.target.z) }
        : {
            x: Number(raw.targetX !== undefined ? raw.targetX : camState.targetX),
            y: Number(raw.targetY !== undefined ? raw.targetY : camState.targetY),
            z: Number(raw.targetZ !== undefined ? raw.targetZ : camState.targetZ),
          });
    if (Number.isFinite(tgt.x) && Number.isFinite(tgt.y) && Number.isFinite(tgt.z)) {
      out.targetX = tgt.x;
      out.targetY = tgt.y;
      out.targetZ = tgt.z;
    }
    if (
      Number.isFinite(Number(raw.theta)) &&
      Number.isFinite(Number(raw.phi)) &&
      Number.isFinite(Number(raw.radius))
    ) {
      out.theta = Number(raw.theta);
      out.phi = Number(raw.phi);
      out.radius = Number(raw.radius);
      return out;
    }
    const pos = Array.isArray(raw.position) && raw.position.length >= 3
      ? { x: Number(raw.position[0]), y: Number(raw.position[1]), z: Number(raw.position[2]) }
      : (raw.position && typeof raw.position === "object"
        ? { x: Number(raw.position.x), y: Number(raw.position.y), z: Number(raw.position.z) }
        : null);
    if (pos && Number.isFinite(pos.x) && Number.isFinite(pos.y) && Number.isFinite(pos.z)) {
      const tx = out.targetX !== undefined ? out.targetX : 0;
      const ty = out.targetY !== undefined ? out.targetY : 0;
      const tz = out.targetZ !== undefined ? out.targetZ : 0;
      const dx = pos.x - tx;
      const dy = pos.y - ty;
      const dz = pos.z - tz;
      const r = Math.sqrt(dx * dx + dy * dy + dz * dz);
      if (r > 0.01) {
        out.radius = r;
        out.phi = Math.max(0.2, Math.min(1.48, Math.acos(Math.max(-1, Math.min(1, dy / r)))));
        out.theta = Math.atan2(dx, dz);
        return out;
      }
    }
    return null;
  }

  function applySceneSpec(spec) {
    if (!spec || typeof spec !== "object") return;
    sceneSpecLoaded = true;
    const rawPresets = spec.camera_presets || spec.cameras || spec.presets || null;
    if (rawPresets && typeof rawPresets === "object") {
      Object.keys(rawPresets).forEach((key) => {
        const parsed = parsePresetObj(rawPresets[key]);
        if (parsed) {
          sceneSpecPresets[key] = parsed;
        }
      });
    }
    const bounds = spec.bounds || spec.bbox || spec.bounding_box || null;
    if (bounds && typeof bounds === "object" && !sceneSpecPresets.overview) {
      const minArr = Array.isArray(bounds.min) ? bounds.min : null;
      const maxArr = Array.isArray(bounds.max) ? bounds.max : null;
      if (minArr && maxArr && minArr.length >= 3 && maxArr.length >= 3) {
        const cx = (Number(minArr[0]) + Number(maxArr[0])) * 0.5;
        const cy = (Number(minArr[1]) + Number(maxArr[1])) * 0.5;
        const cz = (Number(minArr[2]) + Number(maxArr[2])) * 0.5;
        const span = Math.max(
          Math.abs(Number(maxArr[0]) - Number(minArr[0])),
          Math.abs(Number(maxArr[2]) - Number(minArr[2]))
        );
        if (Number.isFinite(cx) && Number.isFinite(cy) && Number.isFinite(cz) && Number.isFinite(span) && span > 0.5) {
          sceneSpecPresets.overview = {
            theta: 0.44,
            phi: 0.94,
            radius: Math.max(6.0, Math.min(24.0, span * 1.32)),
            targetX: cx,
            targetY: cy,
            targetZ: cz,
          };
        }
      }
    }
    if (activeVillaRoot) {
      if (Number.isFinite(Number(spec.scale)) && Number(spec.scale) > 0 && Number(spec.scale) !== 1) {
        const sc = Number(spec.scale);
        activeVillaRoot.scale.set(sc, sc, sc);
      }
      if (typeof activeVillaRoot.updateMatrixWorld === "function") {
        activeVillaRoot.updateMatrixWorld(true);
      }
      recomputeBoundPinAnchors();
      refreshBoardCameraIfActive();
    }
  }

  function loadSceneSpec() {
    if (typeof fetch !== "function") {
      return Promise.resolve(null);
    }
    try {
      return fetch("/hardware/blender/SCENE_SPEC.json", { cache: "no-cache" })
        .then((res) => {
          if (!res || !res.ok) return null;
          return res.json().catch(() => null);
        })
        .then((data) => {
          if (data && typeof data === "object" && data.ok !== false) {
            applySceneSpec(data);
          }
          return data;
        })
        .catch(() => null);
    } catch (_) {
      return Promise.resolve(null);
    }
  }

  function bindGlbLockedNodes(villaRoot) {
    if (!villaRoot || typeof villaRoot.getObjectByName !== "function") return 0;
    if (typeof villaRoot.updateMatrixWorld === "function") {
      villaRoot.updateMatrixWorld(true);
    }
    let boundCount = 0;

    const get = (name) => villaRoot.getObjectByName(name) || null;
    const hideFallback = (key) => {
      if (fallbackHandles[key]) {
        fallbackHandles[key].visible = false;
      }
    };
    const markBound = (name) => {
      if (name && !glbHandles.boundNodes.includes(name)) {
        glbHandles.boundNodes.push(name);
      }
    };

    const glbDoorPivot = get("door_pivot");
    const glbDoorLeaf = get("main_door_leaf");
    if (glbDoorPivot || glbDoorLeaf) {
      boundCount++;
      hideFallback("doorGroup");
      const targetDoor = glbDoorPivot || glbDoorLeaf;
      glbHandles.doorPivot = targetDoor;
      if (glbDoorPivot) markBound("door_pivot");
      if (glbDoorLeaf) markBound("main_door_leaf");
      registerClickable(targetDoor, "main_door");
      if (glbDoorLeaf && glbDoorLeaf !== targetDoor) registerClickable(glbDoorLeaf, "main_door");
      bindPinAnchor("main_door", glbDoorLeaf || glbDoorPivot, 0.3);
    }

    const glbServo = get("SG90_DoorServo");
    if (glbServo) {
      boundCount++;
      markBound("SG90_DoorServo");
      hideFallback("sg90Servo");
      glbHandles.servoMats = cloneNodeMaterials(glbServo);
      registerClickable(glbServo, "main_door");
      bindPinAnchor("mod_sg90_servo", glbServo, 0.28);
    }

    const glbServoHorn = get("sg90_horn_pivot") || get("SG90_WhiteHorn");
    if (glbServoHorn) {
      boundCount++;
      markBound(glbServoHorn.name || "sg90_horn_pivot");
      glbHandles.servoHornPivot = glbServoHorn;
      registerClickable(glbServoHorn, "main_door");
    }

    const glbPsu = get("psu_5v_dc_jack");
    if (glbPsu) {
      boundCount++;
      markBound("psu_5v_dc_jack");
      hideFallback("psu5v");
      glbHandles.psuMats = cloneNodeMaterials(glbPsu);
      bindPinAnchor("mod_psu_5v", glbPsu, 0.26);
    }

    const glbLiving = get("led_living_room");
    if (glbLiving) {
      boundCount++;
      markBound("led_living_room");
      hideFallback("livingLamp");
      glbHandles.livingLedNode = glbLiving;
      glbHandles.livingMats = cloneNodeMaterials(glbLiving).filter((m) => !/collar|sup17|lead|silver/i.test(String((m && m.name) || "")));
      if (!glbHandles.livingMats.length) glbHandles.livingMats = cloneNodeMaterials(glbLiving);
      registerClickable(glbLiving, "living_room_light");
      bindPinAnchor("living_room_light", glbLiving, 0.28);
    }

    const glbBedroom = get("led_bedroom");
    if (glbBedroom) {
      boundCount++;
      markBound("led_bedroom");
      hideFallback("bedLamp");
      glbHandles.bedLedNode = glbBedroom;
      glbHandles.bedMats = cloneNodeMaterials(glbBedroom).filter((m) => !/collar|sup17|lead|silver/i.test(String((m && m.name) || "")));
      if (!glbHandles.bedMats.length) glbHandles.bedMats = cloneNodeMaterials(glbBedroom);
      registerClickable(glbBedroom, "bedroom_light");
      bindPinAnchor("bedroom_light", glbBedroom, 0.28);
    }

    const glbPump = get("pump_unit");
    const glbWaterTube = get("water_tube");
    const glbRelay1 = get("relay1_pump");
    if (glbPump || glbWaterTube || glbRelay1) {
      if (glbPump) {
        boundCount++;
        markBound("pump_unit");
        hideFallback("pumpUnit");
        glbHandles.pumpMats.push(...cloneNodeMaterials(glbPump));
        registerClickable(glbPump, "garden_pump");
        bindPinAnchor("garden_pump", glbPump, 0.35);
      }
      if (glbWaterTube) {
        boundCount++;
        markBound("water_tube");
        hideFallback("waterTube");
        registerClickable(glbWaterTube, "garden_pump");
      }
      if (glbRelay1) {
        boundCount++;
        markBound("relay1_pump");
        hideFallback("relay1");
        glbHandles.relay1Mats = cloneNodeMaterials(glbRelay1);
        registerClickable(glbRelay1, "garden_pump");
        bindPinAnchor("mod_relay1_pump", glbRelay1, 0.26);
      }
    }

    const glbBuzzer = get("buzzer_alarm");
    if (glbBuzzer) {
      boundCount++;
      markBound("buzzer_alarm");
      hideFallback("buzzerAlarm");
      glbHandles.buzzerMats = cloneNodeMaterials(glbBuzzer);
      registerClickable(glbBuzzer, "alarm_siren");
      bindPinAnchor("alarm_siren", glbBuzzer, 0.24);
    }

    const glbRelay2 = get("relay2_speaker");
    const glbPam = get("pam8403_module");
    const glbSpeaker = get("speaker_mini");
    if (glbRelay2 || glbPam || glbSpeaker) {
      if (glbRelay2) {
        boundCount++;
        markBound("relay2_speaker");
        hideFallback("relay2");
        glbHandles.relay2Mats = cloneNodeMaterials(glbRelay2);
        registerClickable(glbRelay2, "speaker_amp");
        bindPinAnchor("mod_relay2_speaker", glbRelay2, 0.26);
      }
      if (glbPam) {
        boundCount++;
        markBound("pam8403_module");
        hideFallback("pam8403");
        glbHandles.pamMats = cloneNodeMaterials(glbPam);
        registerClickable(glbPam, "speaker_amp");
        bindPinAnchor("speaker_amp", glbPam, 0.26);
      }
      if (glbSpeaker) {
        boundCount++;
        markBound("speaker_mini");
        hideFallback("speakerMini");
        glbSpeaker.userData = glbSpeaker.userData || {};
        glbSpeaker.userData._baseScale = glbSpeaker.scale
          ? {
              x: Number.isFinite(Number(glbSpeaker.scale.x)) ? Number(glbSpeaker.scale.x) : 1,
              y: Number.isFinite(Number(glbSpeaker.scale.y)) ? Number(glbSpeaker.scale.y) : 1,
              z: Number.isFinite(Number(glbSpeaker.scale.z)) ? Number(glbSpeaker.scale.z) : 1,
            }
          : { x: 1, y: 1, z: 1 };
        glbHandles.speakerMeshes.push(glbSpeaker);
        glbHandles.speakerMats = cloneNodeMaterials(glbSpeaker);
        registerClickable(glbSpeaker, "speaker_amp");
        bindPinAnchor("mod_speaker_mini", glbSpeaker, 0.24);
        if (!glbPam) {
          bindPinAnchor("speaker_amp", glbSpeaker, 0.24);
        }
      }
    }

    const glbDht = get("sensor_dht11");
    if (glbDht) {
      boundCount++;
      markBound("sensor_dht11");
      hideFallback("dht11");
      bindPinAnchor("sensor_dht11_d2", glbDht, 0.26);
    }

    const glbLm393 = get("soil_lm393_board");
    if (glbLm393) {
      boundCount++;
      markBound("soil_lm393_board");
      hideFallback("soilLm393");
      glbHandles.lm393Mats = cloneNodeMaterials(glbLm393);
      bindPinAnchor("mod_soil_lm393", glbLm393, 0.24);
    }

    const glbSoil = get("sensor_soil");
    if (glbSoil) {
      boundCount++;
      markBound("sensor_soil");
      hideFallback("soilSensor");
      bindPinAnchor("sensor_soil_a0", glbSoil, 0.26);
    }

    const glbKy037 = get("sensor_mic_ky037");
    if (glbKy037) {
      boundCount++;
      markBound("sensor_mic_ky037");
      hideFallback("ky037");
      glbHandles.ky037Mats = cloneNodeMaterials(glbKy037);
      bindPinAnchor("sensor_ky037_d5", glbKy037, 0.24);
    }

    const glbKicadHub = get("kicad_pcb_hub");
    const glbNodEmcu = get("nodemcu_esp8266");
    if (glbKicadHub) {
      boundCount++;
      markBound("kicad_pcb_hub");
      hideFallback("hubCabinet");
      hideFallback("hubBreadboard");
      bindPinAnchor("mod_hub_pcb", glbKicadHub, 0.22);
      if (!glbNodEmcu) {
        bindPinAnchor("board_esp8266", glbKicadHub, 0.36);
      }
    }
    if (glbNodEmcu) {
      boundCount++;
      markBound("nodemcu_esp8266");
      hideFallback("nodemcu");
      bindPinAnchor("board_esp8266", glbNodEmcu, 0.36);
    }

    repositionLedGlowAnchors();

    if (typeof villaRoot.traverse === "function") {
      villaRoot.traverse((node) => {
        if (!node || !node.name) return;
        const isWireNode = /^Wire_|^DupontPlug_/i.test(node.name);
        if (!isWireNode) return;
        const meta = inferGlbWireMeta(node.name);
        if (!meta) return;
        const mats = cloneNodeMaterials(node);
        glbWireEntries.push({
          mesh: node,
          moduleId: meta.moduleId,
          hubRef: meta.hubRef,
          wireKey: meta.wireKey,
          defaultWireId: meta.defaultWireId,
          materials: mats,
        });
        if (/^Wire_/i.test(node.name)) {
          node.userData = node.userData || {};
          node.userData.wireId = meta.defaultWireId;
          if (node.isMesh && !clickableMeshes.includes(node)) {
            clickableMeshes.push(node);
          }
          if (typeof node.traverse === "function") {
            node.traverse((ch) => {
              if (ch && ch.isMesh) {
                ch.userData = ch.userData || {};
                ch.userData.wireId = meta.defaultWireId;
                if (!clickableMeshes.includes(ch)) clickableMeshes.push(ch);
              }
            });
          }
        }
      });
    }
    applyWiringDisplayState();

    refreshBoardCameraIfActive();

    return boundCount;
  }

  function buildGroundAndLoadBlenderVilla() {
    // Mặt đất sân vườn bên ngoài
    const groundGeo = new THREE.PlaneGeometry(34, 30);
    const groundMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.92 });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.14;
    ground.receiveShadow = true;
    scene.add(ground);

    // Lưới nền kiến trúc (Architectural Grid)
    const grid = new THREE.GridHelper(28, 28, 0x1e3a5f, 0x132038);
    grid.position.y = -0.13;
    scene.add(grid);

    // Nạp mô hình Biệt thự & Linh kiện GLB (/static/models/smarthome_villa.glb)
    if (THREE.GLTFLoader) {
      const loader = new THREE.GLTFLoader();
      loader.load(
        "/static/models/smarthome_villa.glb",
        (gltf) => {
          const villaRoot = gltf.scene;
          activeVillaRoot = villaRoot;
          if (villaRoot && typeof villaRoot.traverse === "function") {
            villaRoot.traverse((child) => {
              if (child.isMesh) {
                child.castShadow = true;
                child.receiveShadow = true;
              }
            });
          }
          scene.add(villaRoot);
          const boundCount = bindGlbLockedNodes(villaRoot);
          if (boundCount > 0) {
            loadSceneSpec();
          }
        },
        undefined,
        () => {
          buildHouseArchitectureFallback();
        }
      );
    } else {
      buildHouseArchitectureFallback();
    }
  }

  function buildHouseArchitectureFallback() {
    // Đế móng ngôi nhà (mở rộng thềm trước cho Vườn cây & Trạm mạch ESP8266)
    const baseGeo = new THREE.BoxGeometry(11.6, 0.16, 9.6);
    const baseMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.7 });
    const base = new THREE.Mesh(baseGeo, baseMat);
    base.position.set(0, -0.04, 0.9);
    base.receiveShadow = true;
    scene.add(base);

    // Sàn Phòng Khách (bên trái)
    const lrFloorGeo = new THREE.PlaneGeometry(5.8, 7.2);
    const lrFloorMat = new THREE.MeshStandardMaterial({ color: 0x4a3525, roughness: 0.65 });
    const lrFloor = new THREE.Mesh(lrFloorGeo, lrFloorMat);
    lrFloor.rotation.x = -Math.PI / 2;
    lrFloor.position.set(-2.6, 0.05, 0);
    lrFloor.receiveShadow = true;
    scene.add(lrFloor);

    // Sàn Phòng Ngủ (bên phải)
    const brFloorGeo = new THREE.PlaneGeometry(5.2, 7.2);
    const brFloorMat = new THREE.MeshStandardMaterial({ color: 0x3d2e24, roughness: 0.7 });
    const brFloor = new THREE.Mesh(brFloorGeo, brFloorMat);
    brFloor.rotation.x = -Math.PI / 2;
    brFloor.position.set(2.9, 0.05, 0);
    brFloor.receiveShadow = true;
    scene.add(brFloor);

    // Bậc thềm trước cửa chính
    const porchGeo = new THREE.BoxGeometry(2.6, 0.1, 1.5);
    const porchMat = new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.8 });
    const porch = new THREE.Mesh(porchGeo, porchMat);
    porch.position.set(-1.8, 0.02, 4.35);
    porch.receiveShadow = true;
    scene.add(porch);

    const wallMat = new THREE.MeshStandardMaterial({ color: 0xcbd5e1, roughness: 0.75 });
    const wallTrimMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.5 });

    // Tường sau
    const backWall = new THREE.Mesh(new THREE.BoxGeometry(11.2, 3.4, 0.2), wallMat);
    backWall.position.set(0, 1.7, -3.6);
    backWall.castShadow = true;
    backWall.receiveShadow = true;
    scene.add(backWall);

    // Tường trái
    const leftWall = new THREE.Mesh(new THREE.BoxGeometry(0.2, 3.4, 7.4), wallMat);
    leftWall.position.set(-5.5, 1.7, 0);
    leftWall.castShadow = true;
    leftWall.receiveShadow = true;
    scene.add(leftWall);

    // Tường phải
    const rightWallBack = new THREE.Mesh(new THREE.BoxGeometry(0.2, 3.4, 4.2), wallMat);
    rightWallBack.position.set(5.5, 1.7, -1.6);
    scene.add(rightWallBack);

    const rightWallFrontLow = new THREE.Mesh(new THREE.BoxGeometry(0.2, 1.1, 3.2), wallMat);
    rightWallFrontLow.position.set(5.5, 0.55, 2.1);
    scene.add(rightWallFrontLow);

    // Vách ngăn giữa Phòng Khách & Phòng Ngủ
    const midWallBack = new THREE.Mesh(new THREE.BoxGeometry(0.18, 3.4, 3.2), wallMat);
    midWallBack.position.set(0.3, 1.7, -2.0);
    midWallBack.castShadow = true;
    midWallBack.receiveShadow = true;
    scene.add(midWallBack);

    const midWallFront = new THREE.Mesh(new THREE.BoxGeometry(0.18, 1.3, 2.3), wallMat);
    midWallFront.position.set(0.3, 0.65, 2.45);
    scene.add(midWallFront);

    // Tường mặt tiền quanh Cửa Chính
    const frontLeftPillar = new THREE.Mesh(new THREE.BoxGeometry(2.6, 2.7, 0.22), wallMat);
    frontLeftPillar.position.set(-4.2, 1.35, 3.6);
    scene.add(frontLeftPillar);

    const frontRightPillar = new THREE.Mesh(new THREE.BoxGeometry(1.4, 2.7, 0.22), wallMat);
    frontRightPillar.position.set(-0.3, 1.35, 3.6);
    scene.add(frontRightPillar);

    const frontHeader = new THREE.Mesh(new THREE.BoxGeometry(4.8, 0.5, 0.24), wallTrimMat);
    frontHeader.position.set(-2.2, 2.95, 3.6);
    scene.add(frontHeader);

    // Dầm trần treo Đèn
    const beam1 = new THREE.Mesh(new THREE.BoxGeometry(5.8, 0.12, 0.22), wallTrimMat);
    beam1.position.set(-2.6, 3.35, -0.2);
    scene.add(beam1);

    const beamBed = new THREE.Mesh(new THREE.BoxGeometry(5.2, 0.12, 0.22), wallTrimMat);
    beamBed.position.set(2.9, 3.35, -0.3);
    scene.add(beamBed);

    buildFurniture();
  }

  function buildFurniture() {
    // 1. Thảm phòng khách
    const rug = new THREE.Mesh(
      new THREE.BoxGeometry(3.2, 0.03, 2.4),
      new THREE.MeshStandardMaterial({ color: 0x1e3a5f, roughness: 0.9 })
    );
    rug.position.set(-2.6, 0.06, -0.8);
    rug.receiveShadow = true;
    scene.add(rug);

    // 2. Ghế Sofa phòng khách
    const sofaGroup = new THREE.Group();
    const sofaMat = new THREE.MeshStandardMaterial({ color: 0x3b82f6, roughness: 0.6 });
    const sofaSeat = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.42, 0.95), sofaMat);
    sofaSeat.position.set(0, 0.26, 0);
    sofaSeat.castShadow = true;
    sofaSeat.receiveShadow = true;
    sofaGroup.add(sofaSeat);

    const sofaBack = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.85, 0.22), sofaMat);
    sofaBack.position.set(0, 0.48, -0.38);
    sofaBack.castShadow = true;
    sofaGroup.add(sofaBack);

    const armL = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.62, 0.95), sofaMat);
    armL.position.set(-1.2, 0.36, 0);
    sofaGroup.add(armL);
    const armR = armL.clone();
    armR.position.x = 1.2;
    sofaGroup.add(armR);

    sofaGroup.position.set(-2.6, 0.05, -2.2);
    scene.add(sofaGroup);

    // 3. Bàn trà phòng khách
    const tableTop = new THREE.Mesh(
      new THREE.BoxGeometry(1.5, 0.08, 0.8),
      new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.3 })
    );
    tableTop.position.set(-2.6, 0.45, -0.75);
    tableTop.castShadow = true;
    scene.add(tableTop);

    const tableBase = new THREE.Mesh(
      new THREE.BoxGeometry(1.2, 0.38, 0.55),
      new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.8 })
    );
    tableBase.position.set(-2.6, 0.24, -0.75);
    scene.add(tableBase);

    // 4. Giường ngủ
    const bedGroup = new THREE.Group();
    const woodMat = new THREE.MeshStandardMaterial({ color: 0x5c3a21, roughness: 0.7 });
    const mattressMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.6 });
    const blanketMat = new THREE.MeshStandardMaterial({ color: 0x6366f1, roughness: 0.65 });

    const bedFrame = new THREE.Mesh(new THREE.BoxGeometry(2.5, 0.32, 2.9), woodMat);
    bedFrame.position.set(0, 0.21, 0);
    bedFrame.castShadow = true;
    bedGroup.add(bedFrame);

    const headboard = new THREE.Mesh(new THREE.BoxGeometry(2.5, 1.25, 0.18), woodMat);
    headboard.position.set(0, 0.68, -1.38);
    headboard.castShadow = true;
    bedGroup.add(headboard);

    const mattress = new THREE.Mesh(new THREE.BoxGeometry(2.3, 0.28, 2.65), mattressMat);
    mattress.position.set(0, 0.45, 0.05);
    mattress.receiveShadow = true;
    bedGroup.add(mattress);

    const blanket = new THREE.Mesh(new THREE.BoxGeometry(2.32, 0.3, 1.75), blanketMat);
    blanket.position.set(0, 0.46, 0.5);
    bedGroup.add(blanket);

    const pillow1 = new THREE.Mesh(new THREE.BoxGeometry(0.85, 0.16, 0.48), mattressMat);
    pillow1.position.set(-0.55, 0.64, -0.92);
    bedGroup.add(pillow1);
    const pillow2 = pillow1.clone();
    pillow2.position.x = 0.55;
    bedGroup.add(pillow2);

    bedGroup.position.set(3.0, 0.05, -1.7);
    scene.add(bedGroup);

    const nightStand = new THREE.Mesh(new THREE.BoxGeometry(0.65, 0.58, 0.58), woodMat);
    nightStand.position.set(1.25, 0.34, -2.8);
    scene.add(nightStand);
  }

  function buildSmartDevices() {
    // =========================================================================
    // 1. CỬA CHÍNH (main_door) + SERVO SG90 MÀU XANH DƯƠNG (Chân D1 / GPIO5)
    // =========================================================================
    const doorFallbackGroup = new THREE.Group();
    fallbackHandles.doorGroup = doorFallbackGroup;

    doorPivot = new THREE.Group();
    doorPivot.position.set(-2.85, 0.05, 3.6);

    const doorPanelMat = new THREE.MeshStandardMaterial({
      color: 0x8b4513,
      roughness: 0.45,
      metalness: 0.1,
    });
    const doorPanel = new THREE.Mesh(new THREE.BoxGeometry(1.75, 2.6, 0.12), doorPanelMat);
    doorPanel.position.set(0.875, 1.3, 0);
    doorPanel.castShadow = true;
    doorPivot.add(doorPanel);

    const doorGlass = new THREE.Mesh(
      new THREE.BoxGeometry(0.55, 1.6, 0.14),
      new THREE.MeshStandardMaterial({
        color: 0x7dd3fc,
        transparent: true,
        opacity: 0.45,
        roughness: 0.1,
      })
    );
    doorGlass.position.set(0.875, 1.45, 0);
    doorPivot.add(doorGlass);

    const handle = new THREE.Mesh(
      new THREE.BoxGeometry(0.18, 0.42, 0.2),
      new THREE.MeshStandardMaterial({ color: 0xfacc15, metalness: 0.8, roughness: 0.2 })
    );
    handle.position.set(1.55, 1.25, 0);
    doorPivot.add(handle);

    doorFallbackGroup.add(doorPivot);
    scene.add(doorFallbackGroup);

    // Servo SG90 màu xanh dương lắp đồng tâm trên đỉnh bản lề Cửa chính (Chân D1)
    const sg90Group = new THREE.Group();
    setNodeName(sg90Group, "SG90_DoorServo");
    fallbackHandles.sg90Servo = sg90Group;
    sg90Group.position.set(-2.85, 2.84, 3.6);
    const sg90BlueMat = new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.35, metalness: 0.15 });
    const sg90Body = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.36, 0.22), sg90BlueMat);
    sg90Body.position.set(-0.08, 0.06, 0);
    sg90Group.add(sg90Body);
    const sg90Ears = new THREE.Mesh(new THREE.BoxGeometry(0.58, 0.05, 0.22), sg90BlueMat);
    sg90Ears.position.set(-0.08, -0.02, 0);
    sg90Group.add(sg90Ears);
    const sg90GearBoss = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.12, 16), sg90BlueMat);
    sg90GearBoss.position.set(0, -0.14, 0);
    sg90Group.add(sg90GearBoss);

    servoHornPivot = new THREE.Group();
    setNodeName(servoHornPivot, "sg90_horn_pivot");
    servoHornPivot.position.set(0, -0.2, 0);
    const hornWhiteMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.3 });
    const hornArm = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.04, 0.09), hornWhiteMat);
    hornArm.position.set(0.18, 0, 0);
    servoHornPivot.add(hornArm);
    const hornScrew = new THREE.Mesh(
      new THREE.CylinderGeometry(0.035, 0.035, 0.06, 12),
      new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.8 })
    );
    servoHornPivot.add(hornScrew);
    sg90Group.add(servoHornPivot);
    scene.add(sg90Group);

    // Đèn báo trạng thái khóa cửa
    doorLockLedMat = new THREE.MeshBasicMaterial({ color: 0xef4444 });
    const lockLed = new THREE.Mesh(new THREE.SphereGeometry(0.11, 16, 16), doorLockLedMat);
    lockLed.position.set(-0.85, 1.6, 3.74);
    doorFallbackGroup.add(lockLed);

    doorEntranceLight = new THREE.PointLight(0x4ade80, 0, 5.5);
    doorEntranceLight.position.set(-1.9, 2.4, 3.2);
    scene.add(doorEntranceLight);

    function createLedGlowHalo(coreHex, haloHex) {
      const grp = new THREE.Group();
      const coreMesh = new THREE.Mesh(
        new THREE.SphereGeometry(0.14, 18, 18),
        new THREE.MeshBasicMaterial({
          color: coreHex,
          transparent: true,
          opacity: 0.94,
          depthWrite: false,
        })
      );
      const outerMesh = new THREE.Mesh(
        new THREE.SphereGeometry(0.42, 18, 18),
        new THREE.MeshBasicMaterial({
          color: haloHex,
          transparent: true,
          opacity: 0.36,
          depthWrite: false,
        })
      );
      grp.add(coreMesh);
      grp.add(outerMesh);
      grp.visible = false;
      return grp;
    }

    // =========================================================================
    // 2. ĐÈN PHÒNG KHÁCH (living_room_light — Chân D0 / GPIO16 + trở hạn dòng)
    // =========================================================================
    const livingGroup = new THREE.Group();
    fallbackHandles.livingLamp = livingGroup;
    const lrCord = new THREE.Mesh(
      new THREE.CylinderGeometry(0.03, 0.03, 0.45, 12),
      new THREE.MeshStandardMaterial({ color: 0x334155 })
    );
    lrCord.position.set(-2.6, 3.12, -0.2);
    livingGroup.add(lrCord);

    livingBulbMat = new THREE.MeshStandardMaterial({
      color: 0x475569,
      emissive: 0x000000,
      emissiveIntensity: 0,
      roughness: 0.2,
    });
    const lrBulb = new THREE.Mesh(new THREE.SphereGeometry(0.26, 24, 24), livingBulbMat);
    lrBulb.position.set(-2.6, 2.82, -0.2);
    livingGroup.add(lrBulb);
    scene.add(livingGroup);

    livingLedGlowGroup = createLedGlowHalo(0xfff3b0, 0xfbbf24);
    setNodeName(livingLedGlowGroup, "living_led_glow_halo");
    livingLedGlowGroup.position.set(-2.6, 2.82, -0.2);
    scene.add(livingLedGlowGroup);

    livingPointLight = new THREE.PointLight(0xffd166, 0, 14);
    livingPointLight.position.set(-2.6, 2.6, -0.2);
    livingPointLight.castShadow = !isSoftwareRenderer;
    scene.add(livingPointLight);

    // =========================================================================
    // 3. ĐÈN PHÒNG NGỦ (bedroom_light — Chân D4 / GPIO2, đấu nối an toàn boot)
    // =========================================================================
    const bedLampGroup = new THREE.Group();
    fallbackHandles.bedLamp = bedLampGroup;
    bedBulbMat = new THREE.MeshStandardMaterial({
      color: 0x475569,
      emissive: 0x000000,
      emissiveIntensity: 0,
      roughness: 0.25,
    });
    const bedCeilingLamp = new THREE.Mesh(new THREE.SphereGeometry(0.24, 20, 20), bedBulbMat);
    bedCeilingLamp.position.set(2.9, 2.88, -0.3);
    bedLampGroup.add(bedCeilingLamp);

    bedLampShadeMat = new THREE.MeshStandardMaterial({
      color: 0x64748b,
      emissive: 0x000000,
      emissiveIntensity: 0,
    });
    const nightLampShade = new THREE.Mesh(
      new THREE.ConeGeometry(0.2, 0.28, 16, 1, true),
      bedLampShadeMat
    );
    nightLampShade.position.set(1.25, 0.86, -2.8);
    bedLampGroup.add(nightLampShade);
    scene.add(bedLampGroup);

    bedLedGlowGroup = createLedGlowHalo(0xffe58f, 0xffb703);
    setNodeName(bedLedGlowGroup, "bedroom_led_glow_halo");
    bedLedGlowGroup.position.set(2.9, 2.88, -0.3);
    scene.add(bedLedGlowGroup);

    bedPointLight = new THREE.PointLight(0xffb703, 0, 14);
    bedPointLight.position.set(2.7, 2.5, -0.8);
    bedPointLight.castShadow = !isSoftwareRenderer;
    scene.add(bedPointLight);

    // =========================================================================
    // 4. CÒI BÁO ĐỘNG BUZZER 5V (alarm_siren — Chân D8 / GPIO15)
    // =========================================================================
    const buzzerGroup = new THREE.Group();
    fallbackHandles.buzzerAlarm = buzzerGroup;
    sirenBulbMat = new THREE.MeshStandardMaterial({
      color: 0x7f1d1d,
      emissive: 0x000000,
      emissiveIntensity: 0,
    });
    const sirenMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.18, 0.24, 16), sirenBulbMat);
    sirenMesh.rotation.x = Math.PI / 2;
    sirenMesh.position.set(-0.4, 2.85, 3.74);
    buzzerGroup.add(sirenMesh);

    const buzzerCylinder = new THREE.Mesh(
      new THREE.CylinderGeometry(0.12, 0.12, 0.14, 18),
      new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 0.4 })
    );
    buzzerCylinder.rotation.x = Math.PI / 2;
    buzzerCylinder.position.set(-0.08, 2.85, 3.74);
    buzzerGroup.add(buzzerCylinder);
    scene.add(buzzerGroup);

    sirenPointLight = new THREE.PointLight(0xef4444, 0, 14);
    sirenPointLight.position.set(-0.4, 2.85, 4.1);
    scene.add(sirenPointLight);

    registerClickable(doorPivot, "main_door");
    registerClickable(sg90Group, "main_door");
    registerClickable(lockLed, "main_door");
    registerClickable(lrBulb, "living_room_light");
    registerClickable(lrCord, "living_room_light");
    registerClickable(bedCeilingLamp, "bedroom_light");
    registerClickable(nightLampShade, "bedroom_light");
    registerClickable(sirenMesh, "alarm_siren");
    registerClickable(buzzerCylinder, "alarm_siren");
  }

  /**
   * Dựng trọn bộ Linh kiện Phần cứng Thực tế khớp ảnh tham chiếu:
   * - Bồn cây sân vườn + Máy bơm chìm mini 5V trắng (D6 qua Relay 1 xanh) + Tia nước 3D + Cảm biến đất + LM393 (A0)
   * - Cảm biến Nhiệt độ & Độ ẩm DHT11 xanh dương (D2) trên tường Phòng khách
   * - Trạm Mạch Trung Tâm: PCB Hub DIY v3 (100x80 mm, 0 breadboard) + NodeMCU v2 Amica 0.9" (2x15) + Diode 1N4007 + Tụ C1–C9
   *   + Relay 1 xanh (D6 Bơm) + Relay 2 opto đỏ (D7) + Mạch khuếch đại PAM8403 xanh + Loa tròn bạc mini (D3 PWM)
   *   + Cảm biến âm thanh KY-037 PCB đỏ (D5 DO)
   */
  function buildHardwareKit3D() {
    // =========================================================================
    // A. BỒN CÂY SÂN VƯỜN + MÁY BƠM CHÌM MINI 5V TRẮNG (garden_pump D6) + CẢM BIẾN ĐẤT (A0)
    // =========================================================================
    const gardenGroup = new THREE.Group();
    gardenGroup.position.set(2.45, 0.04, 4.35);

    gardenSoilMat = new THREE.MeshStandardMaterial({ color: 0x451a03, roughness: 0.95 });
    const soilBed = new THREE.Mesh(new THREE.BoxGeometry(2.58, 0.08, 1.02), gardenSoilMat);
    soilBed.position.set(-0.2, 0.45, 0);
    gardenGroup.add(soilBed);

    // Cảm biến độ ẩm đất 2 nhánh vàng đồng + bo mạch xanh LM393 (A0)
    const soilSensorGroup = new THREE.Group();
    fallbackHandles.soilSensor = soilSensorGroup;
    soilSensorGroup.position.set(-0.9, 0.52, 0.32);
    const goldForkMat = new THREE.MeshStandardMaterial({ color: 0xfbbf24, metalness: 0.85, roughness: 0.2 });
    const forkLeft = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.38, 0.015), goldForkMat);
    forkLeft.position.set(-0.06, -0.05, 0);
    soilSensorGroup.add(forkLeft);
    const forkRight = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.38, 0.015), goldForkMat);
    forkRight.position.set(0.06, -0.05, 0);
    soilSensorGroup.add(forkRight);
    const probeTop = new THREE.Mesh(
      new THREE.BoxGeometry(0.22, 0.12, 0.03),
      new THREE.MeshStandardMaterial({ color: 0xd97706, roughness: 0.4 })
    );
    probeTop.position.set(0, 0.16, 0);
    soilSensorGroup.add(probeTop);

    const lm393Group = new THREE.Group();
    setNodeName(lm393Group, "soil_lm393_board");
    fallbackHandles.soilLm393 = lm393Group;
    lm393Group.position.set(-0.9, 0.52, 0.32);
    const lm393Board = new THREE.Mesh(
      new THREE.BoxGeometry(0.26, 0.04, 0.34),
      new THREE.MeshStandardMaterial({ color: 0x1d4ed8, roughness: 0.4 })
    );
    lm393Board.position.set(-0.32, -0.02, 0);
    lm393Group.add(lm393Board);
    const lm393Pot = new THREE.Mesh(
      new THREE.BoxGeometry(0.08, 0.06, 0.08),
      new THREE.MeshStandardMaterial({ color: 0x38bdf8 })
    );
    lm393Pot.position.set(-0.32, 0.03, -0.05);
    lm393Group.add(lm393Pot);
    lm393AlertLedMat = new THREE.MeshBasicMaterial({ color: 0x22c55e });
    const lm393Led = new THREE.Mesh(new THREE.SphereGeometry(0.03, 10, 10), lm393AlertLedMat);
    lm393Led.position.set(-0.25, 0.03, 0.08);
    lm393Group.add(lm393Led);
    gardenGroup.add(soilSensorGroup);
    gardenGroup.add(lm393Group);

    // Bể nước trong suốt + Máy bơm chìm mini 5V màu trắng (Chân D6)
    const pumpFallbackGroup = new THREE.Group();
    fallbackHandles.pumpUnit = pumpFallbackGroup;

    const tankMesh = new THREE.Mesh(
      new THREE.CylinderGeometry(0.42, 0.42, 0.56, 20),
      new THREE.MeshStandardMaterial({
        color: 0x0ea5e9,
        transparent: true,
        opacity: 0.38,
        roughness: 0.15,
      })
    );
    tankMesh.position.set(1.15, 0.28, 0);
    pumpFallbackGroup.add(tankMesh);

    pumpBodyMat = new THREE.MeshStandardMaterial({
      color: 0xf8fafc,
      emissive: 0x000000,
      emissiveIntensity: 0,
      roughness: 0.3,
    });
    const pumpCylinder = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.38, 16), pumpBodyMat);
    pumpCylinder.rotation.z = Math.PI / 2;
    pumpCylinder.position.set(1.15, 0.22, 0);
    pumpFallbackGroup.add(pumpCylinder);

    pumpImpeller = new THREE.Mesh(
      new THREE.BoxGeometry(0.04, 0.22, 0.22),
      new THREE.MeshBasicMaterial({ color: 0x0284c7 })
    );
    pumpImpeller.position.set(1.35, 0.22, 0);
    pumpFallbackGroup.add(pumpImpeller);
    gardenGroup.add(pumpFallbackGroup);

    // Ống dẫn nước từ máy bơm vươn lên trên bồn cây
    const waterTubeGroup = new THREE.Group();
    fallbackHandles.waterTube = waterTubeGroup;
    const pipeVert = new THREE.Mesh(
      new THREE.CylinderGeometry(0.035, 0.035, 0.78, 12),
      new THREE.MeshStandardMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.75 })
    );
    pipeVert.position.set(1.02, 0.62, 0);
    waterTubeGroup.add(pipeVert);

    const pipeHoriz = new THREE.Mesh(
      new THREE.CylinderGeometry(0.035, 0.035, 1.35, 12),
      new THREE.MeshStandardMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.75 })
    );
    pipeHoriz.rotation.z = Math.PI / 2;
    pipeHoriz.position.set(0.35, 0.98, 0);
    waterTubeGroup.add(pipeHoriz);

    const nozzle = new THREE.Mesh(
      new THREE.ConeGeometry(0.08, 0.14, 14),
      new THREE.MeshStandardMaterial({ color: 0x0284c7, metalness: 0.4 })
    );
    nozzle.position.set(-0.28, 0.94, 0);
    waterTubeGroup.add(nozzle);
    gardenGroup.add(waterTubeGroup);

    scene.add(gardenGroup);

    registerClickable(pumpCylinder, "garden_pump");
    registerClickable(pumpImpeller, "garden_pump");
    registerClickable(tankMesh, "garden_pump");
    registerClickable(soilBed, "garden_pump");
    registerClickable(pipeVert, "garden_pump");
    registerClickable(pipeHoriz, "garden_pump");
    registerClickable(nozzle, "garden_pump");

    pumpPointLight = new THREE.PointLight(0x00f5d4, 0, 5.5);
    pumpPointLight.position.set(2.3, 1.25, 4.35);
    scene.add(pumpPointLight);

    const waterCount = 75;
    const wGeo = new THREE.BufferGeometry();
    const wPos = new Float32Array(waterCount * 3);
    for (let i = 0; i < waterCount; i++) {
      const t = Math.random();
      const angle = (Math.random() - 0.5) * Math.PI * 1.4;
      const spread = t * 0.95;
      wPos[i * 3] = 2.17 + Math.cos(angle) * spread;
      wPos[i * 3 + 1] = 1.0 - t * t * 0.52;
      wPos[i * 3 + 2] = 4.35 + Math.sin(angle) * spread * 0.45;
    }
    wGeo.setAttribute("position", new THREE.BufferAttribute(wPos, 3));
    const wMat = new THREE.PointsMaterial({
      color: 0x38bdf8,
      size: 0.11,
      transparent: true,
      opacity: 0.92,
    });
    pumpWaterParticles = new THREE.Points(wGeo, wMat);
    pumpWaterParticles.visible = false;
    scene.add(pumpWaterParticles);

    // =========================================================================
    // B. CẢM BIẾN NHIỆT ĐỘ & ĐỘ ẨM DHT11 MÀU XANH DƯƠNG (Chân D2 / GPIO4)
    // =========================================================================
    const dhtGroup = new THREE.Group();
    fallbackHandles.dht11 = dhtGroup;
    dhtGroup.position.set(0.18, 1.82, -1.1);
    const dhtPcb = new THREE.Mesh(
      new THREE.BoxGeometry(0.04, 0.34, 0.22),
      new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.5 })
    );
    dhtGroup.add(dhtPcb);
    const dhtBlueHousing = new THREE.Mesh(
      new THREE.BoxGeometry(0.11, 0.26, 0.2),
      new THREE.MeshStandardMaterial({ color: 0x06b6d4, roughness: 0.35 })
    );
    dhtBlueHousing.position.set(-0.06, 0.02, 0);
    dhtGroup.add(dhtBlueHousing);
    const dhtLed = new THREE.Mesh(
      new THREE.SphereGeometry(0.025, 10, 10),
      new THREE.MeshBasicMaterial({ color: 0x22c55e })
    );
    dhtLed.position.set(-0.04, -0.12, 0);
    dhtGroup.add(dhtLed);
    scene.add(dhtGroup);

    // =========================================================================
    // C. TRẠM MẠCH TRUNG TÂM PCB-DIRECT (KHÔNG BREADBOARD):
    //    - PCB Hub DIY v3 (100x80mm FR4 xanh) + NodeMCU v2 Amica 0.9" (2x15)
    //    - Hàn trực tiếp C1-C9 (gồm C8, C9), D1-D2 (1N4007), Q1 (S8050), R1-R10
    //    - Relay 1 xanh (D6 Bơm) + Relay 2 opto đỏ (D7) + PAM8403 + Loa + KY-037
    // =========================================================================
    const centralHubGroup = new THREE.Group();
    centralHubGroup.position.set(-0.25, 1.18, 2.45);

    const hubCabinet = new THREE.Mesh(
      new THREE.BoxGeometry(1.18, 0.24, 0.78),
      new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.35, metalness: 0.35 })
    );
    fallbackHandles.hubCabinet = hubCabinet;
    hubCabinet.castShadow = true;
    centralHubGroup.add(hubCabinet);

    // Mạch PCB Hub DIY v3 (100x80mm FR4 xanh lá, KHÔNG dùng breadboard trắng)
    const pcbHubGroup = new THREE.Group();
    fallbackHandles.hubBreadboard = pcbHubGroup;
    pcbHubGroup.position.set(-0.16, 0.145, 0.04);

    const pcbBoardMesh = new THREE.Mesh(
      new THREE.BoxGeometry(0.56, 0.032, 0.44),
      new THREE.MeshStandardMaterial({ color: 0x065f46, roughness: 0.38, metalness: 0.12 })
    );
    pcbHubGroup.add(pcbBoardMesh);

    const pcbCopperRail = new THREE.Mesh(
      new THREE.BoxGeometry(0.52, 0.004, 0.012),
      new THREE.MeshStandardMaterial({ color: 0xd97706, metalness: 0.75, roughness: 0.3 })
    );
    pcbCopperRail.position.set(0, 0.018, 0.17);
    pcbHubGroup.add(pcbCopperRail);

    // Linh kiện bảo vệ hàn trên PCB Hub DIY v3: D1-D2 (1N4007), C1-C9, LED báo nguồn D3
    const diodeBodyMat = new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 0.45 });
    const diodeBandMat = new THREE.MeshStandardMaterial({ color: 0xd1d5db, metalness: 0.8 });
    for (let i = 0; i < 2; i++) {
      const dBody = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.045, 10), diodeBodyMat);
      dBody.rotation.z = Math.PI / 2;
      dBody.position.set(-0.2 + i * 0.08, 0.032, 0.12);
      pcbHubGroup.add(dBody);
      const dBand = new THREE.Mesh(new THREE.CylinderGeometry(0.0125, 0.0125, 0.01, 10), diodeBandMat);
      dBand.rotation.z = Math.PI / 2;
      dBand.position.set(-0.185 + i * 0.08, 0.032, 0.12);
      pcbHubGroup.add(dBand);
    }

    const capGreenMat = new THREE.MeshStandardMaterial({ color: 0x15803d, roughness: 0.35, metalness: 0.25 });
    const capTopMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.85 });
    [-0.14, 0.18, 0.23].forEach((cx) => {
      const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.022, 0.065, 14), capGreenMat);
      cap.position.set(cx, 0.048, -0.11);
      pcbHubGroup.add(cap);
      const capTop = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.006, 14), capTopMat);
      capTop.position.set(cx, 0.082, -0.11);
      pcbHubGroup.add(capTop);
    });

    // Đèn LED chỉ báo D0, D4 & Buzzer D8 trên khối mạch dự phòng
    boardLedMats.d0_living = new THREE.MeshBasicMaterial({ color: 0x450a0a });
    const ledD0 = new THREE.Mesh(new THREE.SphereGeometry(0.022, 10, 10), boardLedMats.d0_living);
    ledD0.position.set(0.14, 0.036, 0.1);
    pcbHubGroup.add(ledD0);

    boardLedMats.d4_bedroom = new THREE.MeshBasicMaterial({ color: 0x422006 });
    const ledD4 = new THREE.Mesh(new THREE.SphereGeometry(0.022, 10, 10), boardLedMats.d4_bedroom);
    ledD4.position.set(0.2, 0.036, 0.1);
    pcbHubGroup.add(ledD4);

    boardLedMats.d8_buzzer = new THREE.MeshBasicMaterial({ color: 0x1f2937 });
    const buzOnPcb = new THREE.Mesh(new THREE.CylinderGeometry(0.032, 0.032, 0.036, 14), boardLedMats.d8_buzzer);
    buzOnPcb.position.set(0.24, 0.036, 0.01);
    pcbHubGroup.add(buzOnPcb);

    centralHubGroup.add(pcbHubGroup);

    // NodeMCU v2 Amica hẹp 0.9" (48.26x25.40mm, 2x15 header) cắm trực tiếp vào đế U1/U2 trên PCB Hub
    const nodemcuGroup = new THREE.Group();
    fallbackHandles.nodemcu = nodemcuGroup;
    nodemcuGroup.position.set(-0.24, 0.195, 0.04);

    const espPcb = new THREE.Mesh(
      new THREE.BoxGeometry(0.32, 0.022, 0.16),
      new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 0.3 })
    );
    nodemcuGroup.add(espPcb);

    const espShield = new THREE.Mesh(
      new THREE.BoxGeometry(0.12, 0.022, 0.11),
      new THREE.MeshStandardMaterial({ color: 0xcbd5e1, metalness: 0.85, roughness: 0.2 })
    );
    espShield.position.set(0.04, 0.022, 0);
    nodemcuGroup.add(espShield);

    const usbPort = new THREE.Mesh(
      new THREE.BoxGeometry(0.045, 0.02, 0.055),
      new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.85 })
    );
    usbPort.position.set(-0.145, 0.018, 0);
    nodemcuGroup.add(usbPort);

    const pinMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.9, roughness: 0.2 });
    for (let p = 0; p < 15; p++) {
      const px = -0.14 + p * 0.02;
      const pinTop = new THREE.Mesh(new THREE.BoxGeometry(0.008, 0.032, 0.008), pinMat);
      pinTop.position.set(px, -0.016, -0.068);
      nodemcuGroup.add(pinTop);
      const pinBot = new THREE.Mesh(new THREE.BoxGeometry(0.008, 0.032, 0.008), pinMat);
      pinBot.position.set(px, -0.016, 0.068);
      nodemcuGroup.add(pinBot);
    }

    boardLedMats.esp_onboard = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });
    const espLed = new THREE.Mesh(new THREE.SphereGeometry(0.015, 10, 10), boardLedMats.esp_onboard);
    espLed.position.set(0.12, 0.022, -0.04);
    nodemcuGroup.add(espLed);

    centralHubGroup.add(nodemcuGroup);

    // Module Relay 1 màu xanh 5V 1 kênh (Chân D6 - Máy bơm tưới cây)
    const relay1Group = new THREE.Group();
    fallbackHandles.relay1 = relay1Group;
    relay1Group.position.set(0.28, 0.155, -0.22);
    const relay1Pcb = new THREE.Mesh(
      new THREE.BoxGeometry(0.18, 0.024, 0.13),
      new THREE.MeshStandardMaterial({ color: 0x1d4ed8, roughness: 0.4 })
    );
    relay1Group.add(relay1Pcb);
    const relay1Coil = new THREE.Mesh(
      new THREE.BoxGeometry(0.1, 0.07, 0.085),
      new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.3 })
    );
    relay1Coil.position.set(-0.02, 0.045, 0);
    relay1Group.add(relay1Coil);
    boardLedMats.d6_relay_blue = new THREE.MeshBasicMaterial({ color: 0x172554 });
    const r1Led = new THREE.Mesh(new THREE.SphereGeometry(0.016, 8, 8), boardLedMats.d6_relay_blue);
    r1Led.position.set(0.06, 0.025, 0.04);
    relay1Group.add(r1Led);
    centralHubGroup.add(relay1Group);
    registerClickable(relay1Group, "garden_pump");

    // Module Relay 2 Opto màu đỏ 5V 1 kênh (Chân D7 - Cấp nguồn 5V cho PAM8403)
    const relay2Group = new THREE.Group();
    fallbackHandles.relay2 = relay2Group;
    relay2Group.position.set(0.04, 0.155, -0.24);
    const relay2Pcb = new THREE.Mesh(
      new THREE.BoxGeometry(0.18, 0.024, 0.13),
      new THREE.MeshStandardMaterial({ color: 0xb91c1c, roughness: 0.4 })
    );
    relay2Group.add(relay2Pcb);
    const relay2Block = new THREE.Mesh(
      new THREE.BoxGeometry(0.095, 0.07, 0.085),
      new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.3 })
    );
    relay2Block.position.set(-0.02, 0.045, 0);
    relay2Group.add(relay2Block);
    const relay2Opto = new THREE.Mesh(
      new THREE.BoxGeometry(0.03, 0.025, 0.03),
      new THREE.MeshStandardMaterial({ color: 0x0f172a })
    );
    relay2Opto.position.set(0.055, 0.02, -0.02);
    relay2Group.add(relay2Opto);
    boardLedMats.d7_relay_red = new THREE.MeshBasicMaterial({ color: 0x450a0a });
    const r2Led = new THREE.Mesh(new THREE.SphereGeometry(0.016, 8, 8), boardLedMats.d7_relay_red);
    r2Led.position.set(0.06, 0.025, 0.04);
    relay2Group.add(r2Led);
    centralHubGroup.add(relay2Group);
    registerClickable(relay2Group, "speaker_amp");

    // Mạch khuếch đại âm thanh PAM8403 màu xanh lá (ảnh close-up bên trái)
    const pamGroup = new THREE.Group();
    fallbackHandles.pam8403 = pamGroup;
    pamGroup.position.set(-0.26, 0.148, -0.24);
    const pamPcb = new THREE.Mesh(
      new THREE.BoxGeometry(0.14, 0.02, 0.12),
      new THREE.MeshStandardMaterial({ color: 0x15803d, roughness: 0.4 })
    );
    pamGroup.add(pamPcb);
    const pamIc = new THREE.Mesh(
      new THREE.BoxGeometry(0.055, 0.018, 0.035),
      new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.3 })
    );
    pamIc.position.set(0, 0.018, 0);
    pamGroup.add(pamIc);
    boardLedMats.d7_pam8403_pwr = new THREE.MeshBasicMaterial({ color: 0x052e16 });
    pamPowerLedMat = boardLedMats.d7_pam8403_pwr;
    const pamLed = new THREE.Mesh(new THREE.SphereGeometry(0.014, 8, 8), boardLedMats.d7_pam8403_pwr);
    pamLed.position.set(0.048, 0.02, 0.04);
    pamGroup.add(pamLed);
    centralHubGroup.add(pamGroup);
    registerClickable(pamGroup, "speaker_amp");

    // Loa tròn bạc mini (khớp ảnh overview: vành kim loại tròn sáng + màng tối + tâm bạc) — nhận PWM D3
    const speakerGroup = new THREE.Group();
    fallbackHandles.speakerMini = speakerGroup;
    speakerGroup.position.set(-0.44, 0.23, -0.22);

    const spkHousing = new THREE.Mesh(
      new THREE.CylinderGeometry(0.11, 0.11, 0.05, 24),
      new THREE.MeshStandardMaterial({ color: 0xd1d5db, metalness: 0.85, roughness: 0.22 })
    );
    spkHousing.rotation.x = Math.PI / 2;
    speakerGroup.add(spkHousing);

    speakerDiaphragmMat = new THREE.MeshStandardMaterial({
      color: 0x334155,
      emissive: 0x000000,
      emissiveIntensity: 0,
      roughness: 0.55,
    });
    speakerConeMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.085, 0.06, 0.02, 22), speakerDiaphragmMat);
    speakerConeMesh.rotation.x = Math.PI / 2;
    speakerConeMesh.position.set(0, 0, 0.022);
    speakerGroup.add(speakerConeMesh);

    const spkDustCap = new THREE.Mesh(
      new THREE.SphereGeometry(0.032, 16, 12),
      new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.9, roughness: 0.15 })
    );
    spkDustCap.position.set(0, 0, 0.028);
    speakerGroup.add(spkDustCap);

    spkLedMat = new THREE.MeshBasicMaterial({ color: 0x1e293b });
    const spkLed = new THREE.Mesh(new THREE.SphereGeometry(0.016, 10, 10), spkLedMat);
    spkLed.position.set(0, 0.12, 0);
    speakerGroup.add(spkLed);

    centralHubGroup.add(speakerGroup);
    registerClickable(speakerGroup, "speaker_amp");

    // Cảm biến âm thanh KY-037 PCB đỏ (ảnh close-up bên phải) — DO nối D5 (GPIO14)
    const ky037Group = new THREE.Group();
    fallbackHandles.ky037 = ky037Group;
    ky037Group.position.set(0.37, 0.155, 0.14);

    const kyPcb = new THREE.Mesh(
      new THREE.BoxGeometry(0.11, 0.02, 0.28),
      new THREE.MeshStandardMaterial({ color: 0xdc2626, roughness: 0.42 })
    );
    ky037Group.add(kyPcb);

    const kyMicCapsule = new THREE.Mesh(
      new THREE.CylinderGeometry(0.042, 0.042, 0.055, 18),
      new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.85, roughness: 0.25 })
    );
    kyMicCapsule.position.set(0, 0.035, 0.095);
    ky037Group.add(kyMicCapsule);

    const kyMicFront = new THREE.Mesh(
      new THREE.CylinderGeometry(0.038, 0.038, 0.008, 16),
      new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 0.9 })
    );
    kyMicFront.position.set(0, 0.064, 0.095);
    ky037Group.add(kyMicFront);

    const kyTrimpot = new THREE.Mesh(
      new THREE.BoxGeometry(0.055, 0.055, 0.06),
      new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.35 })
    );
    kyTrimpot.position.set(0.022, 0.035, 0);
    ky037Group.add(kyTrimpot);

    const kyScrew = new THREE.Mesh(
      new THREE.CylinderGeometry(0.012, 0.012, 0.015, 10),
      new THREE.MeshStandardMaterial({ color: 0xfacc15, metalness: 0.85 })
    );
    kyScrew.position.set(0.022, 0.065, -0.015);
    ky037Group.add(kyScrew);

    const kyIc = new THREE.Mesh(
      new THREE.BoxGeometry(0.035, 0.018, 0.045),
      new THREE.MeshStandardMaterial({ color: 0x0f172a })
    );
    kyIc.position.set(-0.025, 0.018, 0);
    ky037Group.add(kyIc);

    boardLedMats.d5_ky037_do = new THREE.MeshBasicMaterial({ color: 0x431407 });
    const kyDoLed = new THREE.Mesh(new THREE.SphereGeometry(0.016, 10, 10), boardLedMats.d5_ky037_do);
    kyDoLed.position.set(-0.025, 0.022, -0.08);
    ky037Group.add(kyDoLed);

    centralHubGroup.add(ky037Group);

    // Giắc nguồn 5V 2A DC-022 -> cầu đấu vít J1 trên mặt nạ khoang kỹ thuật (fallback)
    const psuFallbackGroup = new THREE.Group();
    setNodeName(psuFallbackGroup, "psu_5v_dc_jack");
    fallbackHandles.psu5v = psuFallbackGroup;
    psuFallbackGroup.position.set(-0.56, 0.14, 0.34);
    const dcJackBarrel = new THREE.Mesh(
      new THREE.CylinderGeometry(0.055, 0.055, 0.14, 16),
      new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 0.35, metalness: 0.4 })
    );
    dcJackBarrel.rotation.x = Math.PI / 2;
    psuFallbackGroup.add(dcJackBarrel);
    const dcJackRing = new THREE.Mesh(
      new THREE.CylinderGeometry(0.068, 0.068, 0.022, 16),
      new THREE.MeshStandardMaterial({ color: 0xcbd5e1, metalness: 0.85, roughness: 0.2 })
    );
    dcJackRing.rotation.x = Math.PI / 2;
    dcJackRing.position.z = 0.065;
    psuFallbackGroup.add(dcJackRing);
    centralHubGroup.add(psuFallbackGroup);

    // Vòng sóng phản hồi KY-037 khi phát hiện vỗ tay / tiếng động lớn
    ky037WaveMat = new THREE.MeshBasicMaterial({
      color: 0xf97316,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.0,
    });
    ky037WaveRing = new THREE.Mesh(new THREE.RingGeometry(0.07, 0.11, 24), ky037WaveMat);
    ky037WaveRing.rotation.x = -Math.PI / 2;
    ky037WaveRing.position.set(0.12, 1.44, 2.59);
    ky037WaveRing.visible = false;
    scene.add(ky037WaveRing);

    scene.add(centralHubGroup);

    // Vòng sóng âm 3D tỏa ra từ Loa tròn bạc PAM8403 khi speaker_amp ON hoặc phát giọng nói
    for (let i = 0; i < 3; i++) {
      const wRingGeo = new THREE.RingGeometry(0.08, 0.13, 24);
      const wRingMat = new THREE.MeshBasicMaterial({
        color: 0x38bdf8,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.0,
      });
      const wRing = new THREE.Mesh(wRingGeo, wRingMat);
      wRing.visible = false;
      scene.add(wRing);
      audioWaveRings.push({ mesh: wRing, mat: wRingMat, phase: i * 0.33 });
    }

    // =========================================================================
    // D. HỆ THỐNG ĐI DÂY ĐIỆN 3D (9 tuyến dây chuẩn hợp đồng 10 chân ESP8266)
    // =========================================================================
    wireConduitGroup = new THREE.Group();

    function add3DWireConduit(key, hexColor, pointsArray, radius = 0.022) {
      const vecs = pointsArray.map((p) => new THREE.Vector3(p[0], p[1], p[2]));
      const curve = new THREE.CatmullRomCurve3(vecs, false, "catmullrom", 0.08);
      const geo = new THREE.TubeGeometry(curve, Math.max(24, vecs.length * 10), radius, 8, false);
      const mat = new THREE.MeshStandardMaterial({
        color: hexColor,
        emissive: hexColor,
        emissiveIntensity: 0.28,
        roughness: 0.35,
        metalness: 0.2,
      });
      wireMats[key] = mat;
      const mesh = new THREE.Mesh(geo, mat);
      mesh.castShadow = false;
      mesh.userData = mesh.userData || {};
      mesh.userData.wireKey = key;
      const conduitWireIds = {
        d1_door: "W03",
        d0_living: "W06",
        d4_bedroom: "W09",
        d6_pump: "W12",
        d8_siren: "W18",
        d7_d3_speaker: "W21",
        d2_dht11: "W31",
        a0_soil: "W35",
        d5_ky037: "W40",
      };
      if (conduitWireIds[key]) {
        mesh.userData.wireId = conduitWireIds[key];
        clickableMeshes.push(mesh);
      }
      wireConduitMeshes[key] = mesh;
      wireConduitGroup.add(mesh);
    }

    // 1. Dây Vàng (D1 / GPIO5) -> Servo SG90 Cửa chính
    add3DWireConduit("d1_door", 0xfacc15, [
      [-0.48, 1.34, 2.45],
      [-0.48, 1.34, 3.55],
      [-0.95, 1.34, 3.58],
      [-0.95, 2.32, 3.58],
    ]);

    // 2. Dây Xanh lá (D0 / GPIO16) -> Đèn Phòng Khách
    add3DWireConduit("d0_living", 0x22c55e, [
      [-0.36, 1.36, 2.45],
      [0.18, 1.36, 2.45],
      [0.18, 3.32, 2.45],
      [0.18, 3.32, -0.2],
      [-2.6, 3.26, -0.2],
    ]);

    // 3. Dây Vàng nhạt (D4 / GPIO2) -> Đèn Phòng Ngủ
    add3DWireConduit("d4_bedroom", 0xfde047, [
      [-0.22, 1.36, 2.45],
      [0.42, 1.36, 2.45],
      [0.42, 3.32, 2.45],
      [0.42, 3.32, -0.3],
      [2.9, 3.24, -0.3],
    ]);

    // 4. Dây Xanh dương (D6 / GPIO12 qua Relay 1 xanh) -> Máy bơm nước sân vườn
    add3DWireConduit("d6_pump", 0x38bdf8, [
      [0.03, 1.28, 2.24],
      [0.28, 0.12, 2.45],
      [0.28, 0.12, 4.35],
      [3.58, 0.12, 4.35],
      [3.58, 0.26, 4.35],
    ]);

    // 5. Dây Đỏ hồng (D8 / GPIO15) -> Còi Báo Động Buzzer 5V
    add3DWireConduit("d8_siren", 0xf43f5e, [
      [-0.3, 1.36, 2.45],
      [-0.3, 1.36, 3.66],
      [-0.3, 2.85, 3.66],
      [-0.12, 2.85, 3.74],
    ]);

    // 6. Dây Ngọc (D7 Relay 2 opto + D3 PWM) -> Mạch PAM8403 & Loa bạc
    add3DWireConduit("d7_d3_speaker", 0x34d399, [
      [-0.21, 1.34, 2.22],
      [-0.48, 1.34, 2.22],
      [-0.69, 1.41, 2.23],
    ], 0.018);

    // 7. Dây Xanh lơ (D2 / GPIO4) -> Cảm biến DHT11 trên tường phòng khách
    add3DWireConduit("d2_dht11", 0x06b6d4, [
      [-0.18, 1.35, 2.45],
      [0.2, 1.82, 2.45],
      [0.2, 1.82, -1.1],
    ]);

    // 8. Dây Cam Vàng (A0 / ADC0) -> Cảm biến độ ẩm đất + LM393
    add3DWireConduit("a0_soil", 0xfb923c, [
      [-0.08, 1.24, 2.45],
      [0.22, 0.09, 2.45],
      [0.22, 0.09, 4.65],
      [1.55, 0.09, 4.65],
      [1.55, 0.54, 4.65],
    ]);

    // 9. Dây Đỏ cam (D5 / GPIO14) -> Cảm biến âm thanh KY-037 DO
    add3DWireConduit("d5_ky037", 0xf97316, [
      [-0.14, 1.34, 2.49],
      [0.12, 1.34, 2.59],
    ], 0.016);

    scene.add(wireConduitGroup);
  }

  function buildFloatingPins() {
    if (!labelsContainer) return;
    labelsContainer.innerHTML = "";
    PIN_META.forEach((m) => {
      pinAnchors[m.id] = new THREE.Vector3(m.pos[0], m.pos[1], m.pos[2]);
      const el = document.createElement("button");
      el.setAttribute("data-id", m.id);
      if (m.moduleId) {
        el.setAttribute("data-module-id", m.moduleId);
      }
      if (m.kind === "sensor" || m.kind === "module") {
        el.className = m.kind === "module" ? "pin-3d sensor-pin module-pin" : "pin-3d sensor-pin";
        el.title = "Bấm để chuyển góc nhìn Camera cận cảnh tới linh kiện này";
        let initVal = m.defaultBadge || "ONLINE";
        if (m.id === "sensor_soil_a0") initVal = `${sensorState.soil_moisture_pct}%`;
        else if (m.id === "sensor_dht11_d2") initVal = `${sensorState.temp_c}°C | ${sensorState.humidity_pct}%`;
        else if (m.id === "sensor_ky037_d5") initVal = sensorState.sound_detected ? "CÓ TIẾNG ĐỘNG!" : "Yên tĩnh";
        else if (m.id === "board_esp8266") initVal = "40 DÂY PCB-DIRECT";
        if (!el.dataset) el.dataset = {};
        el.dataset.hasValue = "true";
        el.setAttribute("data-has-value", "true");
        el.innerHTML = `${m.icon ? `<span class="pin-icon">${m.icon}</span> ` : ""}<span class="pin-name">${m.shortName}:</span> <strong class="pin-state">${initVal}</strong>`;
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          if (m.cam) setCameraView(m.cam);
        });
      } else {
        el.className = "pin-3d off";
        el.title = "Bấm để Bật/Tắt hoặc Đóng/Mở trực tiếp thiết bị này";
        el.style.display = "none";
        if (!el.dataset) el.dataset = {};
        el.dataset.hasValue = "false";
        el.setAttribute("data-has-value", "false");
        el.innerHTML = `${m.icon ? `<span class="pin-icon">${m.icon}</span> ` : ""}<span class="pin-name">${m.shortName}:</span> <strong class="pin-state"></strong>`;
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          if (onDeviceClickCallback) {
            onDeviceClickCallback(m.id);
          }
        });
      }
      labelsContainer.appendChild(el);
      pinElements[m.id] = el;
    });
  }

  function isCompactLabelsViewport() {
    const w =
      (container && container.clientWidth) ||
      (typeof window !== "undefined" && Number(window.innerWidth)) ||
      800;
    return w > 0 && w < 500;
  }

  function computeEffectiveLabelsVisible() {
    if (labelsUserOverride !== null) return Boolean(labelsUserOverride);
    if (currentCameraPreset === "board") return false;
    if (isCompactLabelsViewport()) return false;
    return true;
  }

  function syncLabelsVisibilityUi() {
    labelsVisible = computeEffectiveLabelsVisible();
    if (labelsContainer) {
      if (typeof labelsContainer.setAttribute === "function") {
        labelsContainer.setAttribute("data-labels-visible", labelsVisible ? "true" : "false");
      }
      if (labelsContainer.classList && typeof labelsContainer.classList.toggle === "function") {
        labelsContainer.classList.toggle("labels-hidden", !labelsVisible);
      }
    }
    if (typeof document !== "undefined" && typeof document.getElementById === "function") {
      const btn = document.getElementById("btnToggle3dLabels");
      if (btn) {
        btn.textContent = labelsVisible ? "Ẩn nhãn" : "Hiện nhãn";
        if (typeof btn.setAttribute === "function") {
          btn.setAttribute("aria-pressed", labelsVisible ? "true" : "false");
        }
        if (btn.classList && typeof btn.classList.toggle === "function") {
          btn.classList.toggle("active", labelsVisible);
        }
      }
    }
  }

  function setLabelsVisible(visible) {
    labelsUserOverride = visible === null || visible === undefined ? null : Boolean(visible);
    syncLabelsVisibilityUi();
    updatePinPositions();
    return labelsVisible;
  }

  function toggleLabelsVisible() {
    labelsUserOverride = !labelsVisible;
    syncLabelsVisibilityUi();
    updatePinPositions();
    return labelsVisible;
  }

  function areLabelsVisible() {
    return Boolean(labelsVisible);
  }

  function updatePinPositions() {
    if (!labelsContainer || !renderer) return;
    if (!labelsVisible) {
      PIN_META.forEach((m) => {
        const el = pinElements[m.id];
        if (el) el.style.display = "none";
      });
      return;
    }
    const w = container.clientWidth;
    const h = container.clientHeight;
    const visiblePins = [];

    PIN_META.forEach((m) => {
      const el = pinElements[m.id];
      if (!el) return;
      const v = pinAnchors[m.id].clone().project(camera);
      const stSpan = el.querySelector(".pin-state");
      const hasValProp = el.dataset && el.dataset.hasValue !== undefined ? el.dataset.hasValue : el.getAttribute("data-has-value");
      const hasValue = hasValProp !== "false" && Boolean(stSpan && stSpan.textContent && stSpan.textContent.trim());
      if (!hasValue || v.z > 1) {
        el.style.display = "none";
        return;
      }
      el.style.display = "inline-flex";

      let rawX = (v.x * 0.5 + 0.5) * w;
      let rawY = (-(v.y * 0.5) + 0.5) * h;

      const isMobile = w < 500;
      const chipW = el.offsetWidth || (isMobile ? 86 : 112);
      const chipH = el.offsetHeight || (isMobile ? 16 : 19);
      const halfW = chipW * 0.5;
      const halfH = chipH * 0.5;

      visiblePins.push({
        el,
        rawX,
        rawY,
        x: rawX,
        y: rawY,
        hw: halfW,
        hh: halfH,
      });
    });

    if (!visiblePins.length) return;

    // Bố cục 2 cột bám viền Trái / Phải theo tọa độ chiếu 3D: giữ trung tâm mô hình 3D thông thoáng & 0% chồng lấn nhãn
    const sortedByX = visiblePins.slice().sort((a, b) => a.rawX - b.rawX);
    const leftCount = Math.floor(sortedByX.length / 2);
    const leftCol = sortedByX.slice(0, leftCount).sort((a, b) => a.rawY - b.rawY);
    const rightCol = sortedByX.slice(leftCount).sort((a, b) => a.rawY - b.rawY);

    const padX = 6;
    const topPad = 6;
    const layoutColumn = (col, isLeft, bottomLimit) => {
      if (!col.length) return;
      const availTop = topPad + col[0].hh;
      const availBot = Math.max(availTop, bottomLimit - col[col.length - 1].hh);
      const span = Math.max(0, availBot - availTop);
      const n = col.length;
      for (let i = 0; i < n; i++) {
        const p = col[i];
        p.x = isLeft ? padX + p.hw : w - padX - p.hw;
        p.y = n === 1 ? (availTop + availBot) * 0.5 : availTop + (span * i) / (n - 1);
      }
      // Bảo vệ khoảng cách tối thiểu giữa 2 nhãn kề nhau
      const minGapY = 2;
      for (let i = 1; i < n; i++) {
        const prev = col[i - 1];
        const cur = col[i];
        const needed = prev.y + prev.hh + cur.hh + minGapY;
        if (cur.y < needed) {
          cur.y = needed;
        }
      }
      const overflow = col[n - 1].y + col[n - 1].hh - bottomLimit;
      if (overflow > 0) {
        for (let i = 0; i < n; i++) {
          col[i].y = Math.max(topPad + col[i].hh, col[i].y - overflow);
        }
      }
    };

    // Chừa vùng đáy trái cho nhãn hướng dẫn ".viewport-note"
    layoutColumn(leftCol, true, h - 38);
    layoutColumn(rightCol, false, h - 8);

    visiblePins.forEach((p) => {
      p.el.style.transform = `translate(-50%, -50%) translate(${Math.round(p.x)}px, ${Math.round(p.y)}px)`;
    });
  }

  function isObjectAndAncestorsVisible(obj) {
    let cur = obj;
    while (cur) {
      if (cur.visible === false) return false;
      if (cur === scene) break;
      cur = cur.parent;
    }
    return true;
  }

  function handleRaycastClick(clientX, clientY) {
    if (!renderer || !camera || typeof onDeviceClickCallback !== "function") return;
    const dom = renderer.domElement;
    const rect = dom.getBoundingClientRect();
    if (
      clientX < rect.left ||
      clientX > rect.right ||
      clientY < rect.top ||
      clientY > rect.bottom
    ) {
      return;
    }
    mouseVec.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    mouseVec.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouseVec, camera);
    const intersects = raycaster
      .intersectObjects(clickableMeshes, true)
      .filter((hit) => hit && isObjectAndAncestorsVisible(hit.object));
    if (intersects && intersects.length > 0) {
      let target = intersects[0].object;
      while (target && (!target.userData || !target.userData.deviceId) && target !== scene) {
        target = target.parent;
      }
      if (target && target.userData && target.userData.deviceId) {
        onDeviceClickCallback(target.userData.deviceId);
      } else if (typeof onWireClickCallback === "function") {
        let wireTarget = intersects[0].object;
        while (wireTarget && (!wireTarget.userData || !wireTarget.userData.wireId) && wireTarget !== scene) {
          wireTarget = wireTarget.parent;
        }
        if (wireTarget && wireTarget.userData && wireTarget.userData.wireId) {
          onWireClickCallback(wireTarget.userData.wireId);
        }
      }
    }
  }

  function bindMouseControls() {
    const dom = renderer.domElement;
    dom.addEventListener("mousedown", (e) => {
      isDragging = true;
      camGoal.autoRotate = false;
      mouseDownPos.x = e.clientX;
      mouseDownPos.y = e.clientY;
      prevMouse.x = e.clientX;
      prevMouse.y = e.clientY;
    });

    window.addEventListener("mousemove", (e) => {
      if (!isDragging) return;
      const dx = e.clientX - prevMouse.x;
      const dy = e.clientY - prevMouse.y;
      prevMouse.x = e.clientX;
      prevMouse.y = e.clientY;
      camGoal.theta -= dx * 0.007;
      camGoal.phi = Math.max(0.28, Math.min(1.42, camGoal.phi - dy * 0.006));
    });

    window.addEventListener("mouseup", (e) => {
      if (!isDragging) return;
      isDragging = false;
      const dist = Math.hypot(e.clientX - mouseDownPos.x, e.clientY - mouseDownPos.y);
      if (dist <= 6) {
        handleRaycastClick(e.clientX, e.clientY);
      }
    });

    dom.addEventListener("mousemove", (e) => {
      if (isDragging) return;
      const rect = dom.getBoundingClientRect();
      mouseVec.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouseVec.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(mouseVec, camera);
      const intersects = raycaster
        .intersectObjects(clickableMeshes, true)
        .filter((hit) => hit && isObjectAndAncestorsVisible(hit.object));
      if (intersects && intersects.length > 0) {
        dom.style.cursor = "pointer";
      } else {
        dom.style.cursor = "default";
      }
    });

    let touchStartPos = { x: 0, y: 0 };
    dom.addEventListener(
      "touchstart",
      (e) => {
        if (e.touches.length === 1) {
          isDragging = true;
          camGoal.autoRotate = false;
          const t = e.touches[0];
          touchStartPos.x = t.clientX;
          touchStartPos.y = t.clientY;
          prevMouse.x = t.clientX;
          prevMouse.y = t.clientY;
        }
      },
      { passive: true }
    );

    window.addEventListener(
      "touchmove",
      (e) => {
        if (!isDragging || e.touches.length !== 1) return;
        const t = e.touches[0];
        const dx = t.clientX - prevMouse.x;
        const dy = t.clientY - prevMouse.y;
        prevMouse.x = t.clientX;
        prevMouse.y = t.clientY;
        camGoal.theta -= dx * 0.007;
        camGoal.phi = Math.max(0.28, Math.min(1.42, camGoal.phi - dy * 0.006));
      },
      { passive: true }
    );

    window.addEventListener("touchend", (e) => {
      if (!isDragging) return;
      isDragging = false;
      if (e.changedTouches.length === 1) {
        const t = e.changedTouches[0];
        const dist = Math.hypot(t.clientX - touchStartPos.x, t.clientY - touchStartPos.y);
        if (dist <= 10) {
          handleRaycastClick(t.clientX, t.clientY);
        }
      }
    });

    dom.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        camGoal.radius = Math.max(1.5, Math.min(22.0, camGoal.radius + e.deltaY * 0.008));
      },
      { passive: false }
    );
  }

  function setCameraView(preset) {
    camGoal.autoRotate = false;
    const specCam = preset === "board" ? null : sceneSpecPresets[preset];
    if (specCam) {
      Object.assign(camGoal, specCam);
    } else if (preset === "overview") {
      Object.assign(camGoal, { theta: 0.44, phi: 0.94, radius: 14.8, targetX: 0.1, targetY: 1.0, targetZ: 0.6 });
    } else if (preset === "living") {
      Object.assign(camGoal, { theta: 0.25, phi: 1.02, radius: 8.5, targetX: -2.3, targetY: 1.3, targetZ: -0.9 });
    } else if (preset === "bedroom") {
      Object.assign(camGoal, { theta: -0.35, phi: 0.98, radius: 9.0, targetX: 2.8, targetY: 1.2, targetZ: -1.1 });
    } else if (preset === "door") {
      Object.assign(camGoal, { theta: 0.12, phi: 1.12, radius: 6.8, targetX: -1.9, targetY: 1.5, targetZ: 3.4 });
    } else if (preset === "garden") {
      Object.assign(camGoal, { theta: -0.28, phi: 1.05, radius: 6.2, targetX: 2.4, targetY: 0.65, targetZ: 4.35 });
    } else if (preset === "board") {
      const dynamicBoardCam = computeBoardPresetFromBounds();
      if (dynamicBoardCam) {
        Object.assign(camGoal, dynamicBoardCam);
      } else if (sceneSpecPresets.board) {
        Object.assign(camGoal, sceneSpecPresets.board);
      } else {
        Object.assign(camGoal, { theta: -0.0852, phi: 0.8949, radius: 5.2747, targetX: -3.2, targetY: 0.45, targetZ: 2.6 });
      }
    } else if (preset === "wires") {
      toggleWiringConduits();
    } else if (preset === "rotate") {
      camGoal.autoRotate = !camState.autoRotate;
      camState.autoRotate = camGoal.autoRotate;
    }

    if (preset && preset !== "rotate" && preset !== "wires") {
      currentCameraPreset = preset;
      labelsUserOverride = null;
      syncLabelsVisibilityUi();
      updatePinPositions();
    }

    if (typeof document !== "undefined") {
      const camToolbar = document.querySelector(".camera-toolbar");
      if (camToolbar) {
        const btn = camToolbar.querySelector(`[data-cam="${preset}"]`);
        if (btn) {
          if (preset !== "rotate") {
            camToolbar.querySelectorAll(".btn-cam").forEach((b) => {
              if (b.getAttribute("data-cam") !== "rotate") b.classList.remove("active");
            });
            btn.classList.add("active");
            const lbl = document.getElementById("lblCurrentCameraView") || document.querySelector(".view-label");
            if (lbl) lbl.textContent = btn.textContent.trim();
          } else {
            btn.classList.toggle("active", Boolean(camGoal.autoRotate));
          }
        }
      }
    }
  }

  function toggleWiringConduits() {
    wiringDisplayState.visible = !wiringDisplayState.visible;
    applyWiringDisplayState();
    return wiringDisplayState.visible;
  }

  function setWiresVisible(visible) {
    wiringDisplayState.visible = Boolean(visible);
    applyWiringDisplayState();
    return wiringDisplayState.visible;
  }

  function applyWiringFilter(moduleId, allowedHouse3dKeys) {
    wiringDisplayState.selectedModuleId = moduleId || "all";
    wiringDisplayState.allowedKeys = allowedHouse3dKeys instanceof Set ? allowedHouse3dKeys : null;
    applyWiringDisplayState();
  }

  function highlightWiringStep(wireEntry) {
    wiringDisplayState.activeWire = wireEntry || null;
    applyWiringDisplayState();
  }

  function setWireClickCallback(cb) {
    onWireClickCallback = typeof cb === "function" ? cb : null;
  }

  function getWireInfo(wireId) {
    if (!wireId) return null;
    return contractWireMetaById[wireId] || null;
  }

  function getWiringDisplayState() {
    return {
      visible: Boolean(wiringDisplayState.visible),
      selectedModuleId: wiringDisplayState.selectedModuleId,
      activeWireId: wiringDisplayState.activeWire ? wiringDisplayState.activeWire.wire_id : null,
      activeWireLengthCm:
        wiringDisplayState.activeWire && typeof wiringDisplayState.activeWire.length_cm === "number"
          ? wiringDisplayState.activeWire.length_cm
          : null,
      contractWireCount: contractWireEntries.length,
      glbWireCount: glbWireEntries.length,
      conduitCount: Object.keys(wireConduitMeshes).length,
      totalWires: contractWireEntries.length || glbWireEntries.length || Object.keys(wireConduitMeshes).length,
      breadboardUsed: false,
    };
  }

  function triggerHardwareVoiceWave(frames = 70) {
    audioWaveTimer = frames;
  }

  function applyGlbEmissive(mats, hex, intensity, overrideColorHex) {
    if (!mats || !mats.length) return;
    mats.forEach((m) => {
      if (!m) return;
      if (overrideColorHex !== undefined && m.color && typeof m.color.setHex === "function") {
        if (m.userData === undefined) m.userData = {};
        if (m.userData._origColorHex === undefined && typeof m.color.getHex === "function") {
          m.userData._origColorHex = m.color.getHex();
        }
        if (overrideColorHex !== null) {
          m.color.setHex(overrideColorHex);
        } else if (m.userData._origColorHex !== undefined) {
          m.color.setHex(m.userData._origColorHex);
        }
      }
      if (m.emissive && typeof m.emissive.setHex === "function") {
        m.emissive.setHex(hex);
      }
      if (m.emissiveIntensity !== undefined) {
        m.emissiveIntensity = intensity;
      }
    });
  }

  function updateModulePinBadge(pinId, text, toneClass) {
    const pin = pinElements[pinId];
    if (!pin) return;
    const st = pin.querySelector ? pin.querySelector(".pin-state") : null;
    if (st) st.textContent = text;
    pin.className = toneClass ? `pin-3d sensor-pin module-pin ${toneClass}` : "pin-3d sensor-pin module-pin";
  }

  function updateSensors(mqttSummary, serverConnected = true) {
    if (!mqttSummary) return;
    const soil = mqttSummary.soil_moisture_telemetry || {};
    const dht = mqttSummary.dht11_telemetry || {};
    const espStat = mqttSummary.esp8266_status || {};
    const sound = mqttSummary.sound_telemetry || mqttSummary.ky037_telemetry || {};
    const isOnline = serverConnected !== undefined ? Boolean(serverConnected) : (espStat.online !== false);

    const pinBoard = pinElements["board_esp8266"];
    if (pinBoard) {
      const st = pinBoard.querySelector(".pin-state");
      if (st) {
        st.textContent = isOnline ? "SERVER ONLINE" : "OFFLINE (MẶC ĐỊNH)";
        st.style.color = "";
      }
      pinBoard.className = isOnline ? "pin-3d sensor-pin" : "pin-3d sensor-pin pin-tone-warn";
      pinBoard.style.borderColor = "";
    }
    if (boardLedMats.esp_onboard) {
      boardLedMats.esp_onboard.color.setHex(isOnline ? 0x38bdf8 : 0xf59e0b);
    }

    if (soil.soil_moisture_pct !== undefined) {
      const rawSoil = Number(soil.soil_moisture_pct);
      const safeSoil = Number.isFinite(rawSoil) ? Math.max(0, Math.min(100, rawSoil)) : 62;
      sensorState.soil_moisture_pct = Math.round(safeSoil * 10) / 10;
      sensorState.soil_status = soil.status_label || (safeSoil < 40 ? "Khô" : "Đủ ẩm");
      const pinSoil = pinElements["sensor_soil_a0"];
      if (pinSoil) {
        const st = pinSoil.querySelector(".pin-state");
        if (st) {
          st.textContent = `${sensorState.soil_moisture_pct}% (${sensorState.soil_status})`;
          st.style.color = "";
        }
        pinSoil.className = safeSoil < 40 ? "pin-3d sensor-pin pin-tone-warn" : "pin-3d sensor-pin pin-tone-ok";
        pinSoil.style.borderColor = "";
      }
      if (lm393AlertLedMat) {
        lm393AlertLedMat.color.setHex(safeSoil < 40 ? 0xef4444 : 0x22c55e);
      }
      if (gardenSoilMat && !deviceStates.garden_pump) {
        gardenSoilMat.color.setHex(safeSoil < 40 ? 0x78350f : 0x3b1704);
      }
    }

    if (dht.temp_c !== undefined) {
      sensorState.temp_c = Number(dht.temp_c).toFixed(1);
      sensorState.humidity_pct = Math.round(Number(dht.humidity_pct || 65));
      const pinDht = pinElements["sensor_dht11_d2"];
      if (pinDht) {
        const st = pinDht.querySelector(".pin-state");
        if (st) {
          st.textContent = `${sensorState.temp_c}°C | ${sensorState.humidity_pct}%`;
          st.style.color = "";
        }
        pinDht.className = Number(dht.temp_c) > 31 ? "pin-3d sensor-pin pin-tone-danger" : "pin-3d sensor-pin";
        pinDht.style.borderColor = "";
      }
    }

    const isLoud = Boolean(
      sound.sound_detected || sound.detected || sound.loud_sound || Number(sound.do_state) === 1
    );
    const evCount = Number(sound.event_count || 0);
    if (isLoud || (Number.isFinite(evCount) && evCount > lastSoundEventCount)) {
      ky037PulseTimer = 60;
    }
    if (Number.isFinite(evCount)) {
      lastSoundEventCount = evCount;
      sensorState.event_count = evCount;
    }
    sensorState.sound_detected = isLoud;
    sensorState.do_state = isLoud ? 1 : 0;
    sensorState.sound_status = isLoud ? "CÓ TIẾNG ĐỘNG!" : (sound.status_label || "Yên tĩnh");

    const pinKy = pinElements["sensor_ky037_d5"];
    if (pinKy) {
      const st = pinKy.querySelector(".pin-state");
      if (st) {
        st.textContent = isLoud ? "CÓ TIẾNG ĐỘNG!" : `Yên tĩnh (${sensorState.event_count})`;
        st.style.color = "";
      }
      pinKy.className = isLoud ? "pin-3d sensor-pin pin-tone-warn" : "pin-3d sensor-pin";
      pinKy.style.borderColor = "";
    }
    if (boardLedMats.d5_ky037_do) {
      boardLedMats.d5_ky037_do.color.setHex(isLoud ? 0xf97316 : 0x431407);
    }
    if (wireMats.d5_ky037) {
      wireMats.d5_ky037.emissiveIntensity = isLoud ? 1.55 : 0.28;
    }
    applyGlbEmissive(glbHandles.ky037Mats, isLoud ? 0xf97316 : 0x000000, isLoud ? 1.2 : 0);
  }

  function updateDevices(devicesArray, mqttSummary, serverConnected = true) {
    const isOnline = serverConnected !== undefined ? Boolean(serverConnected) : true;
    let anyStateChanged = false;
    (devicesArray || []).forEach((d) => {
      if (!d || !d.id) return;
      const isActive = d.state === "ON" || d.state === "OPEN";
      if (Object.prototype.hasOwnProperty.call(deviceStates, d.id)) {
        if (deviceStates[d.id] !== isActive) {
          anyStateChanged = true;
        }
        deviceStates[d.id] = isActive;
      }

      const pin = pinElements[d.id];
      if (pin) {
        const isLockedOffline = !isOnline && (d.id === "main_door" || d.id === "alarm_siren");
        const stateVal = isLockedOffline ? "KHÓA OFFLINE" : (d.state ? String(d.state).trim() : "");
        const stSpan = pin.querySelector(".pin-state");
        if (stSpan) {
          stSpan.textContent = stateVal;
          stSpan.style.color = "";
        }
        if (!pin.dataset) pin.dataset = {};
        if (!stateVal) {
          pin.style.display = "none";
          pin.dataset.hasValue = "false";
          pin.setAttribute("data-has-value", "false");
        } else {
          pin.dataset.hasValue = "true";
          pin.setAttribute("data-has-value", "true");
          pin.className = `pin-3d ${isActive ? "on" : "off"}${isLockedOffline ? " pin-offline" : ""}`;
          pin.style.borderColor = "";
        }
      }
    });

    if (mqttSummary) {
      updateSensors(mqttSummary, isOnline);
    }

    // 1. Đèn phòng khách (Chân D0 / GPIO16)
    if (deviceStates.living_room_light) {
      livingBulbMat.color.setHex(0xfffbeb);
      livingBulbMat.emissive.setHex(0xfbbf24);
      livingBulbMat.emissiveIntensity = 2.2;
      livingPointLight.intensity = 3.6;
      if (livingLedGlowGroup) livingLedGlowGroup.visible = true;
      if (boardLedMats.d0_living) boardLedMats.d0_living.color.setHex(0xef4444);
      applyGlbEmissive(glbHandles.livingMats, 0xfbbf24, 3.2, 0xfffbeb);
    } else {
      livingBulbMat.color.setHex(0x475569);
      livingBulbMat.emissive.setHex(0x000000);
      livingBulbMat.emissiveIntensity = 0;
      livingPointLight.intensity = 0;
      if (livingLedGlowGroup) livingLedGlowGroup.visible = false;
      if (boardLedMats.d0_living) boardLedMats.d0_living.color.setHex(0x450a0a);
      applyGlbEmissive(glbHandles.livingMats, 0x000000, 0, null);
    }

    // 2. Đèn phòng ngủ (Chân D4 / GPIO2)
    if (deviceStates.bedroom_light) {
      bedBulbMat.color.setHex(0xfffbeb);
      bedBulbMat.emissive.setHex(0xffb703);
      bedBulbMat.emissiveIntensity = 2.2;
      bedLampShadeMat.emissive.setHex(0xf59e0b);
      bedLampShadeMat.emissiveIntensity = 1.4;
      bedPointLight.intensity = 3.4;
      if (bedLedGlowGroup) bedLedGlowGroup.visible = true;
      if (boardLedMats.d4_bedroom) boardLedMats.d4_bedroom.color.setHex(0xfacc15);
      applyGlbEmissive(glbHandles.bedMats, 0xffb703, 3.2, 0xfffbeb);
    } else {
      bedBulbMat.color.setHex(0x475569);
      bedBulbMat.emissive.setHex(0x000000);
      bedBulbMat.emissiveIntensity = 0;
      bedLampShadeMat.emissive.setHex(0x000000);
      bedLampShadeMat.emissiveIntensity = 0;
      bedPointLight.intensity = 0;
      if (bedLedGlowGroup) bedLedGlowGroup.visible = false;
      if (boardLedMats.d4_bedroom) boardLedMats.d4_bedroom.color.setHex(0x422006);
      applyGlbEmissive(glbHandles.bedMats, 0x000000, 0, null);
    }

    // 3. Cửa chính & Servo SG90 (Chân D1 / GPIO5)
    if (deviceStates.main_door) {
      doorLockLedMat.color.setHex(0x22c55e);
      doorEntranceLight.intensity = 1.6;
      applyGlbEmissive(glbHandles.servoMats, 0x38bdf8, 0.45);
      updateModulePinBadge("mod_sg90_servo", "90° MỞ", "pin-tone-ok");
    } else {
      doorLockLedMat.color.setHex(0xef4444);
      doorEntranceLight.intensity = 0;
      applyGlbEmissive(glbHandles.servoMats, 0x000000, 0);
      updateModulePinBadge("mod_sg90_servo", "0° ĐÓNG", "");
    }

    // 4. Còi báo động Buzzer 5V (Chân D8 / GPIO15)
    if (!deviceStates.alarm_siren) {
      sirenBulbMat.emissive.setHex(0x000000);
      sirenBulbMat.emissiveIntensity = 0;
      sirenPointLight.intensity = 0;
      if (boardLedMats.d8_buzzer) boardLedMats.d8_buzzer.color.setHex(0x1f2937);
      applyGlbEmissive(glbHandles.buzzerMats, 0x000000, 0);
    } else {
      if (boardLedMats.d8_buzzer) boardLedMats.d8_buzzer.color.setHex(0xef4444);
      applyGlbEmissive(glbHandles.buzzerMats, 0xef4444, 1.3);
    }

    // 5. Máy bơm nước mini 5V & Relay 1 xanh (Chân D6 / GPIO12)
    if (deviceStates.garden_pump) {
      if (pumpBodyMat) {
        pumpBodyMat.emissive.setHex(0x0ea5e9);
        pumpBodyMat.emissiveIntensity = 0.85;
      }
      if (pumpWaterParticles) pumpWaterParticles.visible = true;
      if (pumpPointLight) pumpPointLight.intensity = 1.6;
      if (gardenSoilMat) gardenSoilMat.color.setHex(0x271002);
      if (boardLedMats.d6_relay_blue) boardLedMats.d6_relay_blue.color.setHex(0x22c55e);
      applyGlbEmissive(glbHandles.pumpMats, 0x0ea5e9, 0.9);
      applyGlbEmissive(glbHandles.relay1Mats, 0x22c55e, 0.8);
      updateModulePinBadge("mod_relay1_pump", "BẬT", "pin-tone-ok");
    } else {
      if (pumpBodyMat) {
        pumpBodyMat.emissive.setHex(0x000000);
        pumpBodyMat.emissiveIntensity = 0;
      }
      if (pumpWaterParticles) pumpWaterParticles.visible = false;
      if (pumpPointLight) pumpPointLight.intensity = 0;
      if (boardLedMats.d6_relay_blue) boardLedMats.d6_relay_blue.color.setHex(0x172554);
      applyGlbEmissive(glbHandles.pumpMats, 0x000000, 0);
      applyGlbEmissive(glbHandles.relay1Mats, 0x000000, 0);
      updateModulePinBadge("mod_relay1_pump", "TẮT", "");
    }

    // 6. Nguồn mạch loa PAM8403 & Relay 2 opto đỏ (Chân D7 / GPIO13 + PWM D3 / GPIO0)
    if (deviceStates.speaker_amp) {
      if (boardLedMats.d7_relay_red) boardLedMats.d7_relay_red.color.setHex(0xef4444);
      if (boardLedMats.d7_pam8403_pwr) boardLedMats.d7_pam8403_pwr.color.setHex(0x22c55e);
      if (spkLedMat) spkLedMat.color.setHex(0x22d3ee);
      if (speakerDiaphragmMat) {
        speakerDiaphragmMat.emissive.setHex(0x0284c7);
        speakerDiaphragmMat.emissiveIntensity = 0.75;
      }
      applyGlbEmissive(glbHandles.relay2Mats, 0xef4444, 0.8);
      applyGlbEmissive(glbHandles.pamMats, 0x22c55e, 0.9);
      applyGlbEmissive(glbHandles.speakerMats, 0x38bdf8, 0.7);
      updateModulePinBadge("mod_relay2_speaker", "BẬT", "pin-tone-ok");
    } else {
      if (boardLedMats.d7_relay_red) boardLedMats.d7_relay_red.color.setHex(0x450a0a);
      if (boardLedMats.d7_pam8403_pwr) boardLedMats.d7_pam8403_pwr.color.setHex(0x052e16);
      if (spkLedMat) spkLedMat.color.setHex(0x1e293b);
      if (speakerDiaphragmMat) {
        speakerDiaphragmMat.emissive.setHex(0x000000);
        speakerDiaphragmMat.emissiveIntensity = 0;
      }
      applyGlbEmissive(glbHandles.relay2Mats, 0x000000, 0);
      applyGlbEmissive(glbHandles.pamMats, 0x000000, 0);
      applyGlbEmissive(glbHandles.speakerMats, 0x000000, 0);
      updateModulePinBadge("mod_relay2_speaker", "TẮT", "");
    }

    // 7. Làm sáng Đường Dây Điện 3D tương ứng khi thiết bị đang BẬT / MỞ (trừ khi đang highlight hướng dẫn nối dây)
    if (!wiringDisplayState.activeWire) {
      if (wireMats.d1_door) wireMats.d1_door.emissiveIntensity = deviceStates.main_door ? 1.45 : 0.28;
      if (wireMats.d0_living) wireMats.d0_living.emissiveIntensity = deviceStates.living_room_light ? 1.45 : 0.28;
      if (wireMats.d4_bedroom) wireMats.d4_bedroom.emissiveIntensity = deviceStates.bedroom_light ? 1.45 : 0.28;
      if (wireMats.d6_pump) wireMats.d6_pump.emissiveIntensity = deviceStates.garden_pump ? 1.55 : 0.28;
      if (wireMats.d8_siren) wireMats.d8_siren.emissiveIntensity = deviceStates.alarm_siren ? 1.65 : 0.28;
      if (wireMats.d7_d3_speaker) wireMats.d7_d3_speaker.emissiveIntensity = deviceStates.speaker_amp ? 1.55 : 0.28;
    }

    if (deviceStates.speaker_amp || anyStateChanged) {
      triggerHardwareVoiceWave(45);
    }

    updatePinPositions();
  }

  let lastRenderTimeMs = 0;
  let renderedFramesCount = 0;

  function animate(timeMs) {
    requestAnimationFrame(animate);
    if (typeof document !== "undefined" && document.hidden) return;
    const isAutomated =
      isSoftwareRenderer ||
      (typeof navigator !== "undefined" &&
        (Boolean(navigator.webdriver) || /HeadlessChrome/i.test(String(navigator.userAgent || ""))));
    if (isAutomated && renderedFramesCount > 3 && ((timeMs || 0) - lastRenderTimeMs) < 400) {
      return;
    }
    const prevRenderTimeMs = lastRenderTimeMs;
    lastRenderTimeMs = timeMs || 0;
    renderedFramesCount++;
    let dtSec = 0.05;
    let camLerpAlpha = 0.12;
    if (renderedFramesCount > 1 && prevRenderTimeMs > 0 && Number.isFinite(timeMs) && timeMs > prevRenderTimeMs) {
      dtSec = Math.max(0.016, Math.min(0.5, (timeMs - prevRenderTimeMs) / 1000));
      camLerpAlpha = 1 - Math.exp(-7.67 * dtSec);
    }

    // 1. Nội suy góc xoay đồng bộ Cửa Chính & Tay đòn Servo SG90 (Chân D1, 0° đóng / +90° mở vào phòng khách)
    const targetDoorAngle = deviceStates.main_door ? Math.PI / 2 : 0.0;
    const doorLerpAlpha = 1 - Math.exp(-8.0 * dtSec);
    currentDoorAngle += (targetDoorAngle - currentDoorAngle) * doorLerpAlpha;
    if (Math.abs(targetDoorAngle - currentDoorAngle) < 0.005) {
      currentDoorAngle = targetDoorAngle;
    }
    if (doorPivot) {
      doorPivot.rotation.y = currentDoorAngle;
    }
    if (glbHandles.doorPivot) {
      glbHandles.doorPivot.rotation.y = currentDoorAngle;
    }
    if (servoHornPivot) {
      servoHornPivot.rotation.y = currentDoorAngle;
    }
    if (glbHandles.servoHornPivot) {
      glbHandles.servoHornPivot.rotation.y = currentDoorAngle;
    }

    // 2. Đèn chớp Còi Báo Động Buzzer 5V (Chân D8)
    if (deviceStates.alarm_siren) {
      const pulse = (Math.sin((timeMs || 0) * 0.018) + 1) * 0.5;
      sirenBulbMat.emissive.setHex(0xef4444);
      sirenBulbMat.emissiveIntensity = 0.6 + pulse * 2.2;
      sirenPointLight.intensity = pulse * 3.5;
    }

    // 3. Máy bơm nước mini 5V & Hạt tia nước phun tưới cây 3D (Chân D6)
    if (deviceStates.garden_pump) {
      if (pumpImpeller) {
        pumpImpeller.rotation.x += 0.35;
      }
      if (pumpWaterParticles) {
        const wArr = pumpWaterParticles.geometry.attributes.position.array;
        for (let i = 0; i < wArr.length; i += 3) {
          wArr[i + 1] -= 0.035;
          wArr[i] += (Math.random() - 0.52) * 0.025;
          if (wArr[i + 1] < 0.46) {
            const angle = (Math.random() - 0.5) * Math.PI * 1.4;
            const r = Math.random() * 0.85;
            wArr[i] = 2.17 + Math.cos(angle) * r;
            wArr[i + 1] = 0.98;
            wArr[i + 2] = 4.35 + Math.sin(angle) * r * 0.42;
          }
        }
        pumpWaterParticles.geometry.attributes.position.needsUpdate = true;
      }
    }

    // 4. Vòng sóng âm 3D từ Loa bạc PAM8403 (D7/D3)
    const speakerActive = Boolean(deviceStates.speaker_amp || audioWaveTimer > 0);
    if (audioWaveTimer > 0) audioWaveTimer--;
    if (speakerConeMesh) {
      const spkScale = deviceStates.speaker_amp ? (1 + 0.08 * Math.sin((timeMs || 0) * 0.025)) : 1;
      speakerConeMesh.scale.set(spkScale, spkScale, spkScale);
    }
    if (glbHandles.speakerMeshes && glbHandles.speakerMeshes.length) {
      const glbSpkFactor = deviceStates.speaker_amp ? (1 + 0.06 * Math.sin((timeMs || 0) * 0.025)) : 1;
      glbHandles.speakerMeshes.forEach((mesh) => {
        if (!mesh || !mesh.scale || typeof mesh.scale.set !== "function") return;
        const bs = (mesh.userData && mesh.userData._baseScale) || { x: 1, y: 1, z: 1 };
        mesh.scale.set(bs.x * glbSpkFactor, bs.y * glbSpkFactor, bs.z * glbSpkFactor);
      });
    }
    if (speakerActive) {
      if (wireMats.d7_d3_speaker) wireMats.d7_d3_speaker.emissiveIntensity = 1.6;
      audioWaveRings.forEach((w) => {
        w.mesh.visible = true;
        w.phase = (w.phase + 0.04) % 1.0;
        const t = w.phase;
        w.mesh.position.set(-0.69, 1.41 + t * 0.35, 2.23 - t * 0.85);
        w.mesh.lookAt(-1.2, 1.5, 0.5);
        const s = 0.65 + t * 2.4;
        w.mesh.scale.set(s, s, s);
        w.mat.opacity = (1.0 - t) * 0.88;
      });
    } else {
      if (wireMats.d7_d3_speaker) wireMats.d7_d3_speaker.emissiveIntensity = 0.28;
      audioWaveRings.forEach((w) => {
        if (w.mesh.visible) w.mesh.visible = false;
      });
    }

    // 5. Hiệu ứng vòng sóng cảm biến âm thanh KY-037 (D5 DO)
    if (ky037PulseTimer > 0) ky037PulseTimer--;
    if (ky037WaveRing && ky037WaveMat) {
      if (sensorState.sound_detected || ky037PulseTimer > 0) {
        ky037WaveRing.visible = true;
        const phase = ((timeMs || 0) * 0.004) % 1.0;
        const s = 0.8 + phase * 2.6;
        ky037WaveRing.scale.set(s, s, s);
        ky037WaveMat.opacity = (1.0 - phase) * 0.85;
      } else if (ky037WaveRing.visible) {
        ky037WaveRing.visible = false;
      }
    }

    // 6. Cập nhật Camera mượt mà
    if (camGoal.autoRotate) {
      camGoal.theta += 0.0035;
    }
    camState.theta += (camGoal.theta - camState.theta) * camLerpAlpha;
    camState.phi += (camGoal.phi - camState.phi) * camLerpAlpha;
    camState.radius += (camGoal.radius - camState.radius) * camLerpAlpha;
    camState.targetX += (camGoal.targetX - camState.targetX) * camLerpAlpha;
    camState.targetY += (camGoal.targetY - camState.targetY) * camLerpAlpha;
    camState.targetZ += (camGoal.targetZ - camState.targetZ) * camLerpAlpha;

    camera.position.x =
      camState.targetX + camState.radius * Math.sin(camState.phi) * Math.sin(camState.theta);
    camera.position.y = camState.targetY + camState.radius * Math.cos(camState.phi);
    camera.position.z =
      camState.targetZ + camState.radius * Math.sin(camState.phi) * Math.cos(camState.theta);
    camera.lookAt(camState.targetX, camState.targetY, camState.targetZ);

    renderer.render(scene, camera);
    updatePinPositions();
  }

  function onResize() {
    if (!container || !renderer || !camera) return;
    const w = container.clientWidth || 800;
    const h = container.clientHeight || 520;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    refreshBoardCameraIfActive();
    renderer.setSize(w, h);
    syncLabelsVisibilityUi();
    if (scene && typeof renderer.render === "function") {
      renderer.render(scene, camera);
    }
    updatePinPositions();
  }

  function getDebugState() {
    const readMaxEmissive = (mats, fallbackMat) => {
      if (Array.isArray(mats) && mats.length > 0) {
        let best = 0;
        mats.forEach((m) => {
          const val = m && Number.isFinite(Number(m.emissiveIntensity)) ? Number(m.emissiveIntensity) : 0;
          if (val > best) best = val;
        });
        return Math.round(best * 1000) / 1000;
      }
      const fb = fallbackMat && Number.isFinite(Number(fallbackMat.emissiveIntensity)) ? Number(fallbackMat.emissiveIntensity) : 0;
      return Math.round(fb * 1000) / 1000;
    };
    const activeDoorPivot = glbHandles.doorPivot || doorPivot;
    const activeHornPivot = glbHandles.servoHornPivot || servoHornPivot;
    const doorRad =
      activeDoorPivot && activeDoorPivot.rotation && Number.isFinite(Number(activeDoorPivot.rotation.y))
        ? Number(activeDoorPivot.rotation.y)
        : currentDoorAngle;
    const hornRad =
      activeHornPivot && activeHornPivot.rotation && Number.isFinite(Number(activeHornPivot.rotation.y))
        ? Number(activeHornPivot.rotation.y)
        : currentDoorAngle;
    const radToDeg = (r) => Math.round(((r * 180) / Math.PI) * 100) / 100;

    return {
      doorOpen: Boolean(deviceStates.main_door),
      doorAngleDeg: radToDeg(doorRad),
      servoHornAngleDeg: radToDeg(hornRad),
      livingLightOn: Boolean(deviceStates.living_room_light),
      livingLedEmissive: readMaxEmissive(glbHandles.livingMats, livingBulbMat),
      livingPointLightIntensity:
        livingPointLight && Number.isFinite(Number(livingPointLight.intensity)) ? Number(livingPointLight.intensity) : 0,
      bedroomLightOn: Boolean(deviceStates.bedroom_light),
      bedroomLedEmissive: readMaxEmissive(glbHandles.bedMats, bedBulbMat),
      bedroomPointLightIntensity:
        bedPointLight && Number.isFinite(Number(bedPointLight.intensity)) ? Number(bedPointLight.intensity) : 0,
      labelsVisible: Boolean(labelsVisible),
      modulePins: PIN_META.map((m) => {
        const el = pinElements[m.id];
        const stSpan = el && typeof el.querySelector === "function" ? el.querySelector(".pin-state") : null;
        return {
          id: m.id,
          moduleId: m.moduleId || null,
          kind: m.kind,
          label: m.shortName,
          stateText: stSpan ? String(stSpan.textContent || "").trim() : "",
          visible: Boolean(el && el.style && el.style.display && el.style.display !== "none"),
        };
      }),
      boundGlbNodes: glbHandles.boundNodes.slice(),
      contractWireCount: contractWireEntries.length,
      wiresVisible: Boolean(wiringDisplayState.visible),
      breadboardUsed: false,
    };
  }

  return {
    init,
    updateDevices,
    updateSensors,
    triggerHardwareVoiceWave,
    toggleWiringConduits,
    setWiresVisible,
    applyWiringFilter,
    highlightWiringStep,
    setWireClickCallback,
    getWiringDisplayState,
    getWireInfo,
    loadWiringContract3D,
    setCameraView,
    setLabelsVisible,
    toggleLabelsVisible,
    areLabelsVisible,
    getBoardFrameMetrics,
    getDebugState,
    onResize,
    loadSceneSpec,
  };
})();
