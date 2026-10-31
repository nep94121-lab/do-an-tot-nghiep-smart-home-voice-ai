"use strict";

/**
 * Mô hình Ngôi Nhà Thông Minh 3D (Interactive 3D Smart Home Digital Twin)
 * Xây dựng bằng Three.js (WebGL) — Tương hợp 100% với bộ linh kiện thực tế trên bàn & mạch Wokwi:
 *  1. main_door         : Cửa chính + Động cơ Servo SG90 màu xanh (Chân D1) xoay tay đòn 90°
 *  2. living_room_light : Đèn phòng khách (Chân D2 + Trở 220Ω) + PointLight chiếu sáng Sofa
 *  3. bedroom_light     : Đèn phòng ngủ (Chân D7 + Trở 220Ω) + Đèn ngủ đầu giường
 *  4. fan               : Quạt trần 4 cánh (Chân D6 + Module Relay Xanh) quay có quán tính
 *  5. ac                : Điều hòa (Chân D2 Phát IR 38kHz qua Transistor S8050) + Hạt gió lạnh 3D
 *  6. alarm_siren       : Còi báo động Buzzer 5V (Chân D8) + Đèn chớp đỏ khẩn cấp
 *  7. garden_pump       : Máy bơm nước mini 5V (Chân D3 + Module Relay Đỏ + Diode 1N4007)
 *                         + Bồn cây sân vườn + Ống nước + Hạt tia nước phun tưới cây 3D
 *  8. Cảm biến YL-69 + LM393 (Chân A0) cắm trong bồn cây đo độ ẩm đất thời gian thực
 *  9. Cảm biến DHT11 màu xanh (Chân D6) gắn tường phòng khách đo nhiệt độ & độ ẩm
 * 10. Mắt thu Hồng ngoại VS1838B (Chân D5) + LED phát IR 940nm & S8050 (Chân D2) trên bàn trà
 *     kèm hiệu ứng Vòng sóng Tia Hồng ngoại 38kHz 3D bắn lên Điều hòa
 * 11. Trạm Mạch Điều Khiển Trung Tâm 3D (NodeMCU ESP8266 + Breadboard 400 lỗ + 2 Relay Đỏ/Xanh)
 *     đặt tại bàn kỹ thuật trước hiên nhà, có đèn LED trên mạch sáng đúng theo từng chân GPIO!
 */
window.SmartHome3D = (() => {
  let container, labelsContainer;
  let scene, camera, renderer;
  let onDeviceClickCallback = null;

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

  // Trạng thái 7 thiết bị chấp hành (Actuators)
  const deviceStates = {
    main_door: false,         // D1: Servo SG90 (OPEN / CLOSED)
    living_room_light: false, // D2: LED Đỏ + 220Ω (ON / OFF)
    bedroom_light: false,     // D7: LED Vàng + 220Ω (ON / OFF)
    fan: false,               // D6: Relay Xanh 5V (ON / OFF)
    ac: false,                // D2: IR 940nm + S8050 38kHz (ON / OFF)
    alarm_siren: false,       // D8: Buzzer 5V (ON / OFF)
    garden_pump: false,       // D3: Relay Đỏ 5V + Diode 1N4007 + Máy bơm 5V (ON / OFF)
  };

  // Trạng thái 3 cụm cảm biến & mạch (Sensors & Telemetry)
  const sensorState = {
    soil_moisture_pct: 62,
    soil_status: "Đủ ẩm",
    temp_c: 28.5,
    humidity_pct: 65,
    ir_protocol: "COOLIX 38kHz",
    ir_hex: "0xB2BF40",
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

  let bedBulbMat = null;
  let bedLampShadeMat = null;
  let bedPointLight = null;

  let fanBladesGroup = null;
  let fanRingMat = null;
  let fanSpeed = 0;

  let acFlapPivot = null;
  let acLedMat = null;
  let acParticles = null;
  let acCoolLight = null;
  let prevAcState = false;

  let sirenBulbMat = null;
  let sirenPointLight = null;

  // Máy bơm tưới cây (D3) & Bồn cây sân vườn & Cảm biến đất YL-69 (A0)
  let pumpBodyMat = null;
  let pumpImpeller = null;
  let pumpWaterParticles = null;
  let pumpPointLight = null;
  let gardenSoilMat = null;
  let lm393AlertLedMat = null;

  // Tia hồng ngoại 38kHz 3D (D2 -> Điều hòa)
  let irBeamRings = [];
  let irTxLedMat = null;
  let irBlastTimer = 0;

  // Đèn LED báo trạng thái trực tiếp trên Bảng mạch 3D (Breadboard + NodeMCU + 2 Relay)
  const boardLedMats = {
    esp_onboard: null,
    d2_living: null,
    d7_bed: null,
    d3_relay_red: null,
    d6_relay_blue: null,
    d8_buzzer: null,
    d2_ir: null,
  };

  // Điểm neo 3D để gắn nhãn nổi HTML (Floating 3D Pins)
  const pinAnchors = {};
  const pinElements = {};

  // 7 Nhãn Thiết bị (Bấm để Bật/Tắt) + 4 Nhãn Linh kiện Cảm biến/Mạch (Bấm để Zoom cận cảnh)
  const PIN_META = [
    { id: "main_door", kind: "device", icon: "🚪", shortName: "Cửa Servo SG90 (D1)", pos: [-1.85, 2.55, 3.65] },
    { id: "living_room_light", kind: "device", icon: "💡", shortName: "Đèn khách (D2)", pos: [-2.6, 3.18, -0.2] },
    { id: "fan", kind: "device", icon: "🌀", shortName: "Quạt Relay Xanh (D6)", pos: [-2.6, 3.38, -1.8] },
    { id: "ac", kind: "device", icon: "❄️", shortName: "Điều hòa IR (D2)", pos: [-3.2, 2.82, -3.35] },
    { id: "bedroom_light", kind: "device", icon: "🛏️", shortName: "Đèn ngủ (D7)", pos: [2.9, 3.15, -0.3] },
    { id: "alarm_siren", kind: "device", icon: "🚨", shortName: "Còi Buzzer (D8)", pos: [-0.4, 3.05, 3.74] },
    { id: "garden_pump", kind: "device", icon: "💧", shortName: "Máy bơm 5V (D3)", pos: [3.55, 1.15, 4.35] },
    { id: "sensor_soil_a0", kind: "sensor", cam: "garden", icon: "🌱", shortName: "Đất YL-69 (A0)", pos: [1.55, 1.25, 4.35] },
    { id: "sensor_dht11_d6", kind: "sensor", cam: "living", icon: "🌡️", shortName: "DHT11 (D6)", pos: [0.1, 2.15, -1.1] },
    { id: "sensor_ir_d5", kind: "sensor", cam: "living", icon: "📡", shortName: "Thu/Phát IR (D5/D2)", pos: [-2.6, 0.92, -0.75] },
    { id: "board_esp8266", kind: "sensor", cam: "board", icon: "🔌", shortName: "Mạch ESP8266 + Breadboard", pos: [-4.25, 1.45, 4.35] },
  ];

  function init(canvasContainerId, overlayLabelsId, onToggleDevice) {
    container = document.getElementById(canvasContainerId);
    labelsContainer = document.getElementById(overlayLabelsId);
    onDeviceClickCallback = onToggleDevice;
    if (!container || !window.THREE) return;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x080d1a);
    scene.fog = new THREE.FogExp2(0x080d1a, 0.019);

    const w = container.clientWidth || 800;
    const h = container.clientHeight || 520;
    camera = new THREE.PerspectiveCamera(42, w / h, 0.1, 100);

    renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    buildLighting();
    buildHouseArchitecture();
    buildFurniture();
    buildSmartDevices();
    buildHardwareKit3D();
    buildFloatingPins();
    bindMouseControls();

    window.addEventListener("resize", onResize);
    requestAnimationFrame(animate);
  }

  function buildLighting() {
    const hemi = new THREE.HemisphereLight(0x90e0ef, 0x1e293b, 0.48);
    scene.add(hemi);

    const moonDir = new THREE.DirectionalLight(0xcbd5e1, 0.45);
    moonDir.position.set(8, 15, 11);
    moonDir.castShadow = true;
    moonDir.shadow.mapSize.width = 1024;
    moonDir.shadow.mapSize.height = 1024;
    scene.add(moonDir);
  }

  function buildHouseArchitecture() {
    // Mặt đất sân vườn bên ngoài
    const groundGeo = new THREE.PlaneGeometry(30, 26);
    const groundMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.95 });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.12;
    ground.receiveShadow = true;
    scene.add(ground);

    // Lưới nền kỹ thuật số (Digital Twin Grid)
    const grid = new THREE.GridHelper(26, 26, 0x1e3a5f, 0x132038);
    grid.position.y = -0.11;
    scene.add(grid);

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

    // Dầm trần treo Đèn & Quạt
    const beam1 = new THREE.Mesh(new THREE.BoxGeometry(5.8, 0.12, 0.22), wallTrimMat);
    beam1.position.set(-2.6, 3.35, -0.2);
    scene.add(beam1);

    const beam2 = new THREE.Mesh(new THREE.BoxGeometry(5.8, 0.12, 0.22), wallTrimMat);
    beam2.position.set(-2.6, 3.35, -1.8);
    scene.add(beam2);

    const beamBed = new THREE.Mesh(new THREE.BoxGeometry(5.2, 0.12, 0.22), wallTrimMat);
    beamBed.position.set(2.9, 3.35, -0.3);
    scene.add(beamBed);
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

    // 3. Bàn trà phòng khách (nơi đặt cụm Mắt thu IR VS1838B D5 + LED phát IR 940nm D2)
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
    // 1. CỬA CHÍNH (main_door) + ĐỘNG CƠ SERVO SG90 MÀU XANH DƯƠNG (Chân D1)
    // =========================================================================
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

    scene.add(doorPivot);

    // Mô hình 3D Động cơ Servo SG90 màu xanh dương gắn trên đỉnh bản lề Cửa chính (Chân D1)
    const sg90Group = new THREE.Group();
    sg90Group.position.set(-2.85, 2.72, 3.76);
    const sg90BlueMat = new THREE.MeshStandardMaterial({ color: 0x0284c7, roughness: 0.35, metalness: 0.15 });
    const sg90Body = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.28, 0.22), sg90BlueMat);
    sg90Group.add(sg90Body);
    const sg90Ears = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.05, 0.22), sg90BlueMat);
    sg90Ears.position.y = 0.04;
    sg90Group.add(sg90Ears);
    const sg90GearBoss = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.12, 16), sg90BlueMat);
    sg90GearBoss.position.set(0.08, -0.16, 0);
    sg90Group.add(sg90GearBoss);

    // Tay đòn trắng của Servo SG90 (Servo Horn) xoay cùng góc với cánh cửa
    servoHornPivot = new THREE.Group();
    servoHornPivot.position.set(0.08, -0.22, 0);
    const hornWhiteMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.3 });
    const hornArm = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.04, 0.09), hornWhiteMat);
    hornArm.position.set(0.16, 0, 0);
    servoHornPivot.add(hornArm);
    const hornScrew = new THREE.Mesh(
      new THREE.CylinderGeometry(0.035, 0.035, 0.06, 12),
      new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.8 })
    );
    servoHornPivot.add(hornScrew);
    sg90Group.add(servoHornPivot);
    scene.add(sg90Group);

    // Đèn báo trạng thái khóa cửa trên khung
    doorLockLedMat = new THREE.MeshBasicMaterial({ color: 0xef4444 });
    const lockLed = new THREE.Mesh(new THREE.SphereGeometry(0.11, 16, 16), doorLockLedMat);
    lockLed.position.set(-0.85, 1.6, 3.74);
    scene.add(lockLed);

    doorEntranceLight = new THREE.PointLight(0x4ade80, 0, 5.5);
    doorEntranceLight.position.set(-1.9, 2.4, 3.2);
    scene.add(doorEntranceLight);

    // =========================================================================
    // 2. ĐÈN PHÒNG KHÁCH (living_room_light — Chân D2 + Trở 220Ω)
    // =========================================================================
    const lrCord = new THREE.Mesh(
      new THREE.CylinderGeometry(0.03, 0.03, 0.45, 12),
      new THREE.MeshStandardMaterial({ color: 0x334155 })
    );
    lrCord.position.set(-2.6, 3.12, -0.2);
    scene.add(lrCord);

    livingBulbMat = new THREE.MeshStandardMaterial({
      color: 0x475569,
      emissive: 0x000000,
      emissiveIntensity: 0,
      roughness: 0.2,
    });
    const lrBulb = new THREE.Mesh(new THREE.SphereGeometry(0.26, 24, 24), livingBulbMat);
    lrBulb.position.set(-2.6, 2.82, -0.2);
    scene.add(lrBulb);

    livingPointLight = new THREE.PointLight(0xffd166, 0, 12);
    livingPointLight.position.set(-2.6, 2.6, -0.2);
    livingPointLight.castShadow = true;
    scene.add(livingPointLight);

    // =========================================================================
    // 3. QUẠT TRẦN 4 CÁNH (fan — Chân D6 + Module Relay Xanh)
    // =========================================================================
    const fanRod = new THREE.Mesh(
      new THREE.CylinderGeometry(0.04, 0.04, 0.38, 12),
      new THREE.MeshStandardMaterial({ color: 0x475569 })
    );
    fanRod.position.set(-2.6, 3.16, -1.8);
    scene.add(fanRod);

    fanBladesGroup = new THREE.Group();
    fanBladesGroup.position.set(-2.6, 2.95, -1.8);

    fanRingMat = new THREE.MeshBasicMaterial({ color: 0x334155 });
    const fanHub = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.24, 0.12, 20), fanRingMat);
    fanBladesGroup.add(fanHub);

    const bladeMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.4, roughness: 0.4 });
    for (let i = 0; i < 4; i++) {
      const bladeWrap = new THREE.Group();
      bladeWrap.rotation.y = (i * Math.PI) / 2;
      const blade = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.03, 0.22), bladeMat);
      blade.position.set(0.68, 0, 0);
      blade.castShadow = true;
      bladeWrap.add(blade);
      fanBladesGroup.add(bladeWrap);
    }
    scene.add(fanBladesGroup);

    // =========================================================================
    // 4. ĐIỀU HÒA NHIỆT ĐỘ (ac — Chân D2 Phát IR 38kHz) + HẠT GIÓ LẠNH 3D
    // =========================================================================
    const acBody = new THREE.Mesh(
      new THREE.BoxGeometry(1.85, 0.46, 0.34),
      new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.3 })
    );
    acBody.position.set(-3.2, 2.68, -3.35);
    acBody.castShadow = true;
    scene.add(acBody);

    acLedMat = new THREE.MeshBasicMaterial({ color: 0x334155 });
    const acLed = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.08, 0.02), acLedMat);
    acLed.position.set(-2.5, 2.68, -3.17);
    scene.add(acLed);

    acFlapPivot = new THREE.Group();
    acFlapPivot.position.set(-3.2, 2.46, -3.19);
    const flapMesh = new THREE.Mesh(
      new THREE.BoxGeometry(1.75, 0.08, 0.04),
      new THREE.MeshStandardMaterial({ color: 0xcbd5e1 })
    );
    acFlapPivot.add(flapMesh);
    scene.add(acFlapPivot);

    acCoolLight = new THREE.PointLight(0x38bdf8, 0, 6.5);
    acCoolLight.position.set(-3.2, 2.3, -2.7);
    scene.add(acCoolLight);

    const particleCount = 90;
    const pGeo = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    for (let i = 0; i < particleCount; i++) {
      positions[i * 3] = -3.2 + (Math.random() - 0.5) * 1.6;
      positions[i * 3 + 1] = 2.4 - Math.random() * 1.8;
      positions[i * 3 + 2] = -3.1 + Math.random() * 2.4;
    }
    pGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const pMat = new THREE.PointsMaterial({
      color: 0x38bdf8,
      size: 0.09,
      transparent: true,
      opacity: 0.85,
    });
    acParticles = new THREE.Points(pGeo, pMat);
    acParticles.visible = false;
    scene.add(acParticles);

    // =========================================================================
    // 5. ĐÈN PHÒNG NGỦ (bedroom_light — Chân D7 + Trở 220Ω)
    // =========================================================================
    bedBulbMat = new THREE.MeshStandardMaterial({
      color: 0x475569,
      emissive: 0x000000,
      emissiveIntensity: 0,
      roughness: 0.25,
    });
    const bedCeilingLamp = new THREE.Mesh(new THREE.SphereGeometry(0.24, 20, 20), bedBulbMat);
    bedCeilingLamp.position.set(2.9, 2.88, -0.3);
    scene.add(bedCeilingLamp);

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
    scene.add(nightLampShade);

    bedPointLight = new THREE.PointLight(0xffb703, 0, 11);
    bedPointLight.position.set(2.7, 2.5, -0.8);
    bedPointLight.castShadow = true;
    scene.add(bedPointLight);

    // =========================================================================
    // 6. CÒI BÁO ĐỘNG BUZZER 5V & ĐÈN CHỚP (alarm_siren — Chân D8)
    // =========================================================================
    sirenBulbMat = new THREE.MeshStandardMaterial({
      color: 0x7f1d1d,
      emissive: 0x000000,
      emissiveIntensity: 0,
    });
    const sirenMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.18, 0.24, 16), sirenBulbMat);
    sirenMesh.rotation.x = Math.PI / 2;
    sirenMesh.position.set(-0.4, 2.85, 3.74);
    scene.add(sirenMesh);

    // Thân còi Buzzer tròn màu đen gắn kế bên đèn báo động
    const buzzerCylinder = new THREE.Mesh(
      new THREE.CylinderGeometry(0.12, 0.12, 0.14, 18),
      new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 0.4 })
    );
    buzzerCylinder.rotation.x = Math.PI / 2;
    buzzerCylinder.position.set(-0.08, 2.85, 3.74);
    scene.add(buzzerCylinder);

    sirenPointLight = new THREE.PointLight(0xef4444, 0, 14);
    sirenPointLight.position.set(-0.4, 2.85, 4.1);
    scene.add(sirenPointLight);
  }

  /**
   * Dựng trọn bộ Linh kiện Phần cứng Thực tế còn thiếu trong cảnh 3D:
   * - Khu vườn trước nhà + Máy bơm nước mini 5V (D3) + Tia nước 3D + Cảm biến độ ẩm đất YL-69 & LM393 (A0)
   * - Cảm biến Nhiệt độ & Độ ẩm DHT11 màu xanh (D6) trên tường Phòng khách
   * - Cụm Mắt thu Hồng ngoại VS1838B (D5) + Bóng LED phát IR 940nm & S8050 (D2) trên bàn trà + Tia IR 38kHz 3D
   * - Trạm Mạch Điều Khiển Trung Tâm 3D (NodeMCU ESP8266 + Breadboard 400 lỗ + 2 Module Relay Đỏ D3 & Xanh D6)
   */
  function buildHardwareKit3D() {
    // =========================================================================
    // A. BỒN CÂY SÂN VƯỜN + MÁY BƠM NƯỚC MINI 5V (garden_pump D3) + CẢM BIẾN ĐẤT YL-69 (A0)
    // =========================================================================
    const gardenGroup = new THREE.Group();
    gardenGroup.position.set(2.45, 0.04, 4.35);

    // Thành bồn cây bằng gỗ/đá
    const planterBox = new THREE.Mesh(
      new THREE.BoxGeometry(2.8, 0.46, 1.25),
      new THREE.MeshStandardMaterial({ color: 0x78350f, roughness: 0.8 })
    );
    planterBox.position.set(-0.2, 0.23, 0);
    planterBox.castShadow = true;
    planterBox.receiveShadow = true;
    gardenGroup.add(planterBox);

    // Lớp đất trồng cây (đổi màu đậm/nhạt theo độ ẩm đất A0 và khi bật máy bơm D3)
    gardenSoilMat = new THREE.MeshStandardMaterial({ color: 0x451a03, roughness: 0.95 });
    const soilBed = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.12, 1.05), gardenSoilMat);
    soilBed.position.set(-0.2, 0.43, 0);
    gardenGroup.add(soilBed);

    // 3 Bụi cây xanh trong bồn
    const leafMat1 = new THREE.MeshStandardMaterial({ color: 0x16a34a, roughness: 0.6 });
    const leafMat2 = new THREE.MeshStandardMaterial({ color: 0x22c55e, roughness: 0.55 });
    const stemMat = new THREE.MeshStandardMaterial({ color: 0x5c3a21, roughness: 0.8 });
    [-0.95, -0.25, 0.45].forEach((px, idx) => {
      const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.06, 0.35, 10), stemMat);
      stem.position.set(px, 0.58, 0);
      gardenGroup.add(stem);

      const foliage1 = new THREE.Mesh(
        new THREE.SphereGeometry(0.28 + (idx === 1 ? 0.06 : 0), 16, 16),
        idx % 2 === 0 ? leafMat1 : leafMat2
      );
      foliage1.position.set(px, 0.82, 0);
      foliage1.castShadow = true;
      gardenGroup.add(foliage1);

      const foliage2 = new THREE.Mesh(new THREE.SphereGeometry(0.2, 14, 14), leafMat2);
      foliage2.position.set(px + 0.12, 0.98, 0.08);
      gardenGroup.add(foliage2);
    });

    // CẢM BIẾN ĐỘ ẨM ĐẤT YL-69 (2 nhánh vàng đồng cắm vào đất) + MẠCH SO SÁNH LM393 (Chân A0)
    const yl69Group = new THREE.Group();
    yl69Group.position.set(-0.9, 0.52, 0.32);
    const goldForkMat = new THREE.MeshStandardMaterial({ color: 0xfbbf24, metalness: 0.85, roughness: 0.2 });
    const forkLeft = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.38, 0.015), goldForkMat);
    forkLeft.position.set(-0.06, -0.05, 0);
    yl69Group.add(forkLeft);
    const forkRight = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.38, 0.015), goldForkMat);
    forkRight.position.set(0.06, -0.05, 0);
    yl69Group.add(forkRight);
    const probeTop = new THREE.Mesh(
      new THREE.BoxGeometry(0.22, 0.12, 0.03),
      new THREE.MeshStandardMaterial({ color: 0xd97706, roughness: 0.4 })
    );
    probeTop.position.set(0, 0.16, 0);
    yl69Group.add(probeTop);

    // Bo mạch xanh LM393 gắn cạnh đầu dò YL-69
    const lm393Board = new THREE.Mesh(
      new THREE.BoxGeometry(0.26, 0.04, 0.34),
      new THREE.MeshStandardMaterial({ color: 0x1d4ed8, roughness: 0.4 })
    );
    lm393Board.position.set(-0.32, -0.02, 0);
    yl69Group.add(lm393Board);
    const lm393Pot = new THREE.Mesh(
      new THREE.BoxGeometry(0.08, 0.06, 0.08),
      new THREE.MeshStandardMaterial({ color: 0x38bdf8 })
    );
    lm393Pot.position.set(-0.32, 0.03, -0.05);
    yl69Group.add(lm393Pot);
    lm393AlertLedMat = new THREE.MeshBasicMaterial({ color: 0x22c55e });
    const lm393Led = new THREE.Mesh(new THREE.SphereGeometry(0.03, 10, 10), lm393AlertLedMat);
    lm393Led.position.set(-0.25, 0.03, 0.08);
    yl69Group.add(lm393Led);
    gardenGroup.add(yl69Group);

    // BỂ NƯỚC TRONG SUỐT + MÁY BƠM NƯỚC MINI 5V MÀU TRẮNG (Chân D3) + ỐNG NƯỚC TƯỚI CÂY
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
    gardenGroup.add(tankMesh);

    // Thân Máy bơm nước mini 5V nằm ngang màu trắng ngà
    pumpBodyMat = new THREE.MeshStandardMaterial({
      color: 0xf8fafc,
      emissive: 0x000000,
      emissiveIntensity: 0,
      roughness: 0.3,
    });
    const pumpCylinder = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.38, 16), pumpBodyMat);
    pumpCylinder.rotation.z = Math.PI / 2;
    pumpCylinder.position.set(1.15, 0.22, 0);
    gardenGroup.add(pumpCylinder);

    // Cánh quạt nước bên đầu máy bơm
    pumpImpeller = new THREE.Mesh(
      new THREE.BoxGeometry(0.04, 0.22, 0.22),
      new THREE.MeshBasicMaterial({ color: 0x0284c7 })
    );
    pumpImpeller.position.set(1.35, 0.22, 0);
    gardenGroup.add(pumpImpeller);

    // Ống dẫn nước từ máy bơm vươn lên trên bồn cây
    const pipeVert = new THREE.Mesh(
      new THREE.CylinderGeometry(0.035, 0.035, 0.78, 12),
      new THREE.MeshStandardMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.75 })
    );
    pipeVert.position.set(1.02, 0.62, 0);
    gardenGroup.add(pipeVert);

    const pipeHoriz = new THREE.Mesh(
      new THREE.CylinderGeometry(0.035, 0.035, 1.35, 12),
      new THREE.MeshStandardMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.75 })
    );
    pipeHoriz.rotation.z = Math.PI / 2;
    pipeHoriz.position.set(0.35, 0.98, 0);
    gardenGroup.add(pipeHoriz);

    // Đầu vòi phun tưới cây
    const nozzle = new THREE.Mesh(
      new THREE.ConeGeometry(0.08, 0.14, 14),
      new THREE.MeshStandardMaterial({ color: 0x0284c7, metalness: 0.4 })
    );
    nozzle.position.set(-0.28, 0.94, 0);
    gardenGroup.add(nozzle);

    scene.add(gardenGroup);

    // Ánh sáng xanh ngọc & Hệ thống Hạt Tia Nước 3D (Water Spray Particle System) khi Máy bơm D3 = ON
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
    // B. CẢM BIẾN NHIỆT ĐỘ & ĐỘ ẨM DHT11 MÀU XANH DƯƠNG (Chân D6) TRÊN TƯỜNG PHÒNG KHÁCH
    // =========================================================================
    const dhtGroup = new THREE.Group();
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
    // C. CỤM MẮT THU HỒNG NGOẠI VS1838B (D5) + LED PHÁT IR 940nm & S8050 (D2) TRÊN BÀN TRÀ
    // =========================================================================
    const irModuleGroup = new THREE.Group();
    irModuleGroup.position.set(-2.6, 0.51, -0.75);

    const irBaseBoard = new THREE.Mesh(
      new THREE.BoxGeometry(0.46, 0.04, 0.3),
      new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.4 })
    );
    irModuleGroup.add(irBaseBoard);

    // Mắt thu VS1838B (vỏ sắt đen có vòm cầu) — Chân D5
    const vs1838Body = new THREE.Mesh(
      new THREE.BoxGeometry(0.1, 0.14, 0.09),
      new THREE.MeshStandardMaterial({ color: 0x334155, metalness: 0.7, roughness: 0.3 })
    );
    vs1838Body.position.set(-0.12, 0.08, 0.05);
    irModuleGroup.add(vs1838Body);
    const vs1838Dome = new THREE.Mesh(
      new THREE.SphereGeometry(0.045, 12, 12),
      new THREE.MeshStandardMaterial({ color: 0x090d16, roughness: 0.1 })
    );
    vs1838Dome.position.set(-0.12, 0.09, 0.09);
    irModuleGroup.add(vs1838Dome);

    // Transistor S8050 TO-92 đen kích dòng phát IR
    const s8050Mesh = new THREE.Mesh(
      new THREE.CylinderGeometry(0.04, 0.04, 0.09, 12),
      new THREE.MeshStandardMaterial({ color: 0x111827 })
    );
    s8050Mesh.position.set(0.02, 0.06, 0);
    irModuleGroup.add(s8050Mesh);

    // Bóng LED phát Hồng ngoại IR 940nm (Chân D2) hướng chéo lên Điều hòa
    irTxLedMat = new THREE.MeshStandardMaterial({
      color: 0xa855f7,
      emissive: 0x9333ea,
      emissiveIntensity: 0.4,
      transparent: true,
      opacity: 0.9,
    });
    const irTxBulb = new THREE.Mesh(new THREE.SphereGeometry(0.055, 14, 14), irTxLedMat);
    irTxBulb.position.set(0.14, 0.09, -0.05);
    irModuleGroup.add(irTxBulb);
    scene.add(irModuleGroup);

    // Vòng sóng Tia Hồng ngoại 38kHz 3D bắn từ Bàn trà (-2.46, 0.6, -0.8) lên Điều hòa (-3.2, 2.6, -3.2)
    for (let i = 0; i < 4; i++) {
      const ringGeo = new THREE.RingGeometry(0.06, 0.11, 20);
      const ringMat = new THREE.MeshBasicMaterial({
        color: 0xd946ef,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.0,
      });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.visible = false;
      scene.add(ring);
      irBeamRings.push({ mesh: ring, mat: ringMat, phase: i * 0.25 });
    }

    // =========================================================================
    // D. TRẠM MẠCH ĐIỀU KHIỂN TRUNG TÂM 3D (ĐỒNG BỘ 1:1 VỚI MẠCH WOKWI & BREADBOARD 400 LỖ)
    //    Gồm: NodeMCU ESP8266 30-pin + Breadboard 400 lỗ + 3 Điện trở (220Ω, 1kΩ, 220Ω)
    //    + Transistor S8050 TO-92 + LED Đỏ/Vàng/IR 940nm + Mắt thu VS1838B (D5) + DHT11 (D6)
    //    + Còi Buzzer 5V (D8) + Relay Đỏ 5V (D3) + Diode 1N4007 chống xung ngược + Relay Xanh (D6)
    //    + Chiết áp Potentiometer (A0) + Remote Hồng ngoại 38kHz + Hệ thống Dây cắm Jumper 3D
    // =========================================================================
    const stationGroup = new THREE.Group();
    stationGroup.position.set(-4.15, 0.04, 4.35);

    // Bàn kỹ thuật đặt mạch (rộng rãi để bày đủ toàn bộ linh kiện như trang /wokwi)
    const benchTop = new THREE.Mesh(
      new THREE.BoxGeometry(2.55, 0.08, 1.48),
      new THREE.MeshStandardMaterial({ color: 0x161f30, roughness: 0.45 })
    );
    benchTop.position.set(0, 0.68, 0);
    benchTop.castShadow = true;
    benchTop.receiveShadow = true;
    stationGroup.add(benchTop);

    // Viền kim loại quanh mặt bàn kỹ thuật
    const benchBorder = new THREE.Mesh(
      new THREE.BoxGeometry(2.59, 0.04, 1.52),
      new THREE.MeshStandardMaterial({ color: 0x38bdf8, metalness: 0.6, roughness: 0.3 })
    );
    benchBorder.position.set(0, 0.67, 0);
    stationGroup.add(benchBorder);

    const benchLegGeo = new THREE.BoxGeometry(0.1, 0.66, 1.32);
    const benchLegMat = new THREE.MeshStandardMaterial({ color: 0x334155 });
    const legL = new THREE.Mesh(benchLegGeo, benchLegMat);
    legL.position.set(-1.12, 0.33, 0);
    stationGroup.add(legL);
    const legR = legL.clone();
    legR.position.x = 1.12;
    stationGroup.add(legR);

    // Hàm tiện ích tạo Điện trở cắm 3D (Through-Hole Resistor có 4 vòng màu + 2 chân kim loại)
    function makeResistor3D(x, y, z, band1Hex, band2Hex, band3Hex) {
      const rGrp = new THREE.Group();
      rGrp.position.set(x, y, z);
      const leadMat = new THREE.MeshStandardMaterial({ color: 0xcbd5e1, metalness: 0.85, roughness: 0.2 });
      const leadHoriz = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.14, 8), leadMat);
      leadHoriz.rotation.z = Math.PI / 2;
      rGrp.add(leadHoriz);
      const leadLegL = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.045, 8), leadMat);
      leadLegL.position.set(-0.068, -0.02, 0);
      rGrp.add(leadLegL);
      const leadLegR = leadLegL.clone();
      leadLegR.position.x = 0.068;
      rGrp.add(leadLegR);

      const bodyMesh = new THREE.Mesh(
        new THREE.CylinderGeometry(0.018, 0.018, 0.075, 12),
        new THREE.MeshStandardMaterial({ color: 0xfde68a, roughness: 0.35 })
      );
      bodyMesh.rotation.z = Math.PI / 2;
      rGrp.add(bodyMesh);

      const bGeo = new THREE.CylinderGeometry(0.019, 0.019, 0.009, 12);
      [-0.02, -0.005, 0.01, 0.024].forEach((bx, idx) => {
        const col = idx === 0 ? band1Hex : idx === 1 ? band2Hex : idx === 2 ? band3Hex : 0xd97706;
        const bMesh = new THREE.Mesh(bGeo, new THREE.MeshBasicMaterial({ color: col }));
        bMesh.rotation.z = Math.PI / 2;
        bMesh.position.x = bx;
        rGrp.add(bMesh);
      });
      return rGrp;
    }

    // Hàm tiện ích tạo Dây cắm Jumper 3D uốn cong giữa 2 tọa độ trên bàn mạch
    function addJumperWire3D(pStart, pEnd, hexColor, arcHeight = 0.11) {
      const mid1 = new THREE.Vector3(
        pStart[0] + (pEnd[0] - pStart[0]) * 0.28,
        Math.max(pStart[1], pEnd[1]) + arcHeight,
        pStart[2] + (pEnd[2] - pStart[2]) * 0.28
      );
      const mid2 = new THREE.Vector3(
        pStart[0] + (pEnd[0] - pStart[0]) * 0.72,
        Math.max(pStart[1], pEnd[1]) + arcHeight,
        pStart[2] + (pEnd[2] - pStart[2]) * 0.72
      );
      const curve = new THREE.CatmullRomCurve3([
        new THREE.Vector3(pStart[0], pStart[1], pStart[2]),
        mid1,
        mid2,
        new THREE.Vector3(pEnd[0], pEnd[1], pEnd[2]),
      ]);
      const tubeGeo = new THREE.TubeGeometry(curve, 18, 0.0085, 8, false);
      const tubeMat = new THREE.MeshStandardMaterial({ color: hexColor, roughness: 0.35, metalness: 0.1 });
      const wireMesh = new THREE.Mesh(tubeGeo, tubeMat);
      stationGroup.add(wireMesh);
    }

    // -------------------------------------------------------------------------
    // 1) BO MẠCH NODEMCU ESP8266 (ESP-12E, CP2102, ĐỦ 30 CHÂN MẠ VÀNG)
    // -------------------------------------------------------------------------
    const espX = -0.82;
    const espZ = -0.08;
    const espPcb = new THREE.Mesh(
      new THREE.BoxGeometry(0.46, 0.045, 0.84),
      new THREE.MeshStandardMaterial({ color: 0x111827, roughness: 0.4 })
    );
    espPcb.position.set(espX, 0.745, espZ);
    stationGroup.add(espPcb);

    // Cổng Micro-USB kim loại bạc + nút RST & FLASH + chip CP2102 + AMS1117
    const usbPort = new THREE.Mesh(
      new THREE.BoxGeometry(0.13, 0.035, 0.09),
      new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.85, roughness: 0.2 })
    );
    usbPort.position.set(espX, 0.775, espZ - 0.39);
    stationGroup.add(usbPort);

    const btnRst = new THREE.Mesh(
      new THREE.BoxGeometry(0.05, 0.025, 0.04),
      new THREE.MeshStandardMaterial({ color: 0xf8fafc })
    );
    btnRst.position.set(espX - 0.12, 0.775, espZ - 0.35);
    stationGroup.add(btnRst);
    const btnFlash = btnRst.clone();
    btnFlash.position.x = espX + 0.12;
    stationGroup.add(btnFlash);

    const cp2102Chip = new THREE.Mesh(
      new THREE.BoxGeometry(0.08, 0.02, 0.08),
      new THREE.MeshStandardMaterial({ color: 0x090d16 })
    );
    cp2102Chip.position.set(espX, 0.772, espZ - 0.26);
    stationGroup.add(cp2102Chip);

    // Nắp sắt bạc chip Wi-Fi ESP-12E + Anten chữ Z vàng đồng
    const esp12Can = new THREE.Mesh(
      new THREE.BoxGeometry(0.28, 0.038, 0.32),
      new THREE.MeshStandardMaterial({ color: 0xcbd5e1, metalness: 0.85, roughness: 0.2 })
    );
    esp12Can.position.set(espX, 0.785, espZ + 0.08);
    stationGroup.add(esp12Can);

    const antTrace = new THREE.Mesh(
      new THREE.BoxGeometry(0.24, 0.01, 0.09),
      new THREE.MeshStandardMaterial({ color: 0xfacc15, metalness: 0.8, roughness: 0.25 })
    );
    antTrace.position.set(espX, 0.771, espZ + 0.31);
    stationGroup.add(antTrace);

    // 2 Hàng chân vàng 30-pin (15 chân Trái & 15 chân Phải) dọc hai bên NodeMCU
    const goldPinMat = new THREE.MeshStandardMaterial({ color: 0xfacc15, metalness: 0.9, roughness: 0.15 });
    const pinGeo = new THREE.BoxGeometry(0.018, 0.042, 0.018);
    for (let p = 0; p < 15; p++) {
      const pz = espZ - 0.35 + p * 0.05;
      const pL = new THREE.Mesh(pinGeo, goldPinMat);
      pL.position.set(espX - 0.195, 0.775, pz);
      stationGroup.add(pL);
      const pR = new THREE.Mesh(pinGeo, goldPinMat);
      pR.position.set(espX + 0.195, 0.775, pz);
      stationGroup.add(pR);
    }

    // Đèn LED xanh dương onboard của ESP8266
    boardLedMats.esp_onboard = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });
    const espLed = new THREE.Mesh(new THREE.SphereGeometry(0.026, 10, 10), boardLedMats.esp_onboard);
    espLed.position.set(espX + 0.09, 0.81, espZ + 0.18);
    stationGroup.add(espLed);

    // -------------------------------------------------------------------------
    // 2) BẢNG CẮM BREADBOARD 400 LỖ MÀU TRẮNG + ĐẦY ĐỦ LINH KIỆN CẮM TRÊN MẶT
    // -------------------------------------------------------------------------
    const bbX = -0.02;
    const bbZ = -0.1;
    const bbBody = new THREE.Mesh(
      new THREE.BoxGeometry(0.94, 0.055, 0.64),
      new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.32 })
    );
    bbBody.position.set(bbX, 0.748, bbZ);
    stationGroup.add(bbBody);

    // Rãnh lõm giữa Breadboard (IC Channel)
    const bbGroove = new THREE.Mesh(
      new THREE.BoxGeometry(0.92, 0.012, 0.045),
      new THREE.MeshStandardMaterial({ color: 0xcbd5e1, roughness: 0.6 })
    );
    bbGroove.position.set(bbX, 0.776, bbZ);
    stationGroup.add(bbGroove);

    // Đường rãnh nguồn Cam (+3.3V trên), Đỏ (+5V dưới) và Xanh dương (GND)
    const railOrangeTop = new THREE.Mesh(
      new THREE.BoxGeometry(0.88, 0.008, 0.02),
      new THREE.MeshBasicMaterial({ color: 0xfb923c })
    );
    railOrangeTop.position.set(bbX, 0.78, bbZ - 0.27);
    stationGroup.add(railOrangeTop);

    const railRedBot = new THREE.Mesh(
      new THREE.BoxGeometry(0.88, 0.008, 0.02),
      new THREE.MeshBasicMaterial({ color: 0xef4444 })
    );
    railRedBot.position.set(bbX, 0.78, bbZ + 0.25);
    stationGroup.add(railRedBot);

    const railBlueTop = new THREE.Mesh(
      new THREE.BoxGeometry(0.88, 0.008, 0.02),
      new THREE.MeshBasicMaterial({ color: 0x2563eb })
    );
    railBlueTop.position.set(bbX, 0.78, bbZ - 0.23);
    stationGroup.add(railBlueTop);
    const railBlueBot = railBlueTop.clone();
    railBlueBot.position.z = bbZ + 0.28;
    stationGroup.add(railBlueBot);

    // --- NỬA TRÊN BREADBOARD (Hàng a..e): ---
    // (2.1) Cột 4–9: Điện trở 220Ω (Đỏ-Đỏ-Nâu) + LED Đỏ 5mm (Đèn khách D2)
    stationGroup.add(makeResistor3D(bbX - 0.34, 0.805, bbZ - 0.11, 0xef4444, 0xef4444, 0x78350f));
    boardLedMats.d2_living = new THREE.MeshBasicMaterial({ color: 0x450a0a });
    const bbLedD2 = new THREE.Mesh(new THREE.CylinderGeometry(0.032, 0.036, 0.075, 14), boardLedMats.d2_living);
    bbLedD2.position.set(bbX - 0.24, 0.815, bbZ - 0.14);
    stationGroup.add(bbLedD2);

    // (2.2) Cột 12–18: Điện trở 1kΩ (Nâu-Đen-Đỏ) + Transistor S8050 TO-92 + LED Phát IR 940nm (D2)
    stationGroup.add(makeResistor3D(bbX - 0.08, 0.805, bbZ - 0.11, 0x78350f, 0x111827, 0xef4444));
    const s8050Bb = new THREE.Mesh(
      new THREE.CylinderGeometry(0.032, 0.032, 0.068, 12),
      new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.3 })
    );
    s8050Bb.position.set(bbX + 0.02, 0.812, bbZ - 0.14);
    stationGroup.add(s8050Bb);

    boardLedMats.d2_ir = new THREE.MeshBasicMaterial({ color: 0x581c87 });
    const bbLedIr = new THREE.Mesh(new THREE.CylinderGeometry(0.032, 0.036, 0.075, 14), boardLedMats.d2_ir);
    bbLedIr.position.set(bbX + 0.09, 0.815, bbZ - 0.14);
    stationGroup.add(bbLedIr);

    // (2.3) Cột 22–26: Điện trở 220Ω (Đỏ-Đỏ-Nâu) + LED Vàng 5mm (Đèn ngủ D7)
    stationGroup.add(makeResistor3D(bbX + 0.22, 0.805, bbZ - 0.11, 0xef4444, 0xef4444, 0x78350f));
    boardLedMats.d7_bed = new THREE.MeshBasicMaterial({ color: 0x422006 });
    const bbLedD7 = new THREE.Mesh(new THREE.CylinderGeometry(0.032, 0.036, 0.075, 14), boardLedMats.d7_bed);
    bbLedD7.position.set(bbX + 0.33, 0.815, bbZ - 0.14);
    stationGroup.add(bbLedD7);

    // --- NỬA DƯỚI BREADBOARD (Hàng f..j): ---
    // (2.4) Cột 6–8: Mắt thu hồng ngoại VS1838B (Chân D5) trên Breadboard
    const bbVs1838 = new THREE.Mesh(
      new THREE.BoxGeometry(0.085, 0.11, 0.065),
      new THREE.MeshStandardMaterial({ color: 0x1e293b, metalness: 0.65, roughness: 0.3 })
    );
    bbVs1838.position.set(bbX - 0.26, 0.83, bbZ + 0.11);
    stationGroup.add(bbVs1838);
    const bbVsDome = new THREE.Mesh(
      new THREE.SphereGeometry(0.032, 12, 12),
      new THREE.MeshStandardMaterial({ color: 0x090d16, roughness: 0.1 })
    );
    bbVsDome.position.set(bbX - 0.26, 0.84, bbZ + 0.145);
    stationGroup.add(bbVsDome);

    // (2.5) Cột 15–18: Cảm biến DHT11 / DHT22 (Chân D6) cắm trên Breadboard
    const bbDhtHousing = new THREE.Mesh(
      new THREE.BoxGeometry(0.12, 0.14, 0.065),
      new THREE.MeshStandardMaterial({ color: 0x06b6d4, roughness: 0.35 })
    );
    bbDhtHousing.position.set(bbX + 0.02, 0.845, bbZ + 0.11);
    stationGroup.add(bbDhtHousing);

    // (2.6) Cột 24–25: Còi báo động Buzzer 5V tròn đen (Chân D8) trên Breadboard
    boardLedMats.d8_buzzer = new THREE.MeshBasicMaterial({ color: 0x111827 });
    const bbBuzzer = new THREE.Mesh(new THREE.CylinderGeometry(0.065, 0.065, 0.075, 16), boardLedMats.d8_buzzer);
    bbBuzzer.position.set(bbX + 0.28, 0.815, bbZ + 0.11);
    stationGroup.add(bbBuzzer);
    const bbBuzzerHole = new THREE.Mesh(
      new THREE.CylinderGeometry(0.018, 0.018, 0.08, 10),
      new THREE.MeshBasicMaterial({ color: 0x475569 })
    );
    bbBuzzerHole.position.set(bbX + 0.28, 0.817, bbZ + 0.11);
    stationGroup.add(bbBuzzerHole);

    // -------------------------------------------------------------------------
    // 3) MODULE RELAY ĐỎ 5V (SONGLE) + DIODE 1N4007 CHỐNG XUNG NGƯỢC (D3) & RELAY XANH (D6)
    // -------------------------------------------------------------------------
    const relayRedPcb = new THREE.Mesh(
      new THREE.BoxGeometry(0.42, 0.04, 0.3),
      new THREE.MeshStandardMaterial({ color: 0xb91c1c, roughness: 0.45 })
    );
    relayRedPcb.position.set(0.78, 0.745, -0.24);
    stationGroup.add(relayRedPcb);

    const relayRedCube = new THREE.Mesh(
      new THREE.BoxGeometry(0.22, 0.14, 0.17),
      new THREE.MeshStandardMaterial({ color: 0x1d4ed8, roughness: 0.35 })
    );
    relayRedCube.position.set(0.76, 0.825, -0.24);
    stationGroup.add(relayRedCube);

    // Domino 3 cổng NO/COM/NC màu xanh lá & Jumper H/L màu vàng trên Relay Đỏ
    const relayDomino = new THREE.Mesh(
      new THREE.BoxGeometry(0.07, 0.11, 0.16),
      new THREE.MeshStandardMaterial({ color: 0x15803d })
    );
    relayDomino.position.set(0.93, 0.81, -0.24);
    stationGroup.add(relayDomino);

    const relayJumper = new THREE.Mesh(
      new THREE.BoxGeometry(0.06, 0.05, 0.04),
      new THREE.MeshBasicMaterial({ color: 0xeab308 })
    );
    relayJumper.position.set(0.75, 0.78, -0.12);
    stationGroup.add(relayJumper);

    boardLedMats.d3_relay_red = new THREE.MeshBasicMaterial({ color: 0x450a0a });
    const relayRedLed = new THREE.Mesh(new THREE.SphereGeometry(0.028, 10, 10), boardLedMats.d3_relay_red);
    relayRedLed.position.set(0.62, 0.78, -0.14);
    stationGroup.add(relayRedLed);

    // Con Diode 1N4007 đen có vạch trắng bạc Cathode mắc chống xung ngược cạnh Relay Đỏ (D3)
    const diodeGroup = new THREE.Group();
    diodeGroup.position.set(1.08, 0.79, -0.24);
    const diodeLead = new THREE.Mesh(
      new THREE.CylinderGeometry(0.006, 0.006, 0.16, 8),
      new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.85 })
    );
    diodeLead.rotation.z = Math.PI / 2;
    diodeGroup.add(diodeLead);
    const diodeBody = new THREE.Mesh(
      new THREE.CylinderGeometry(0.02, 0.02, 0.08, 12),
      new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.3 })
    );
    diodeBody.rotation.z = Math.PI / 2;
    diodeGroup.add(diodeBody);
    const diodeStripe = new THREE.Mesh(
      new THREE.CylinderGeometry(0.021, 0.021, 0.014, 12),
      new THREE.MeshBasicMaterial({ color: 0xe2e8f0 })
    );
    diodeStripe.rotation.z = Math.PI / 2;
    diodeStripe.position.x = 0.022;
    diodeGroup.add(diodeStripe);
    stationGroup.add(diodeGroup);

    // Module Relay Xanh (D6 - Quạt trần)
    const relayBluePcb = new THREE.Mesh(
      new THREE.BoxGeometry(0.42, 0.04, 0.3),
      new THREE.MeshStandardMaterial({ color: 0x1d4ed8, roughness: 0.45 })
    );
    relayBluePcb.position.set(0.78, 0.745, 0.18);
    stationGroup.add(relayBluePcb);
    const relayBlueCube = relayRedCube.clone();
    relayBlueCube.position.set(0.76, 0.825, 0.18);
    stationGroup.add(relayBlueCube);
    boardLedMats.d6_relay_blue = new THREE.MeshBasicMaterial({ color: 0x172554 });
    const relayBlueLed = new THREE.Mesh(new THREE.SphereGeometry(0.028, 10, 10), boardLedMats.d6_relay_blue);
    relayBlueLed.position.set(0.62, 0.78, 0.28);
    stationGroup.add(relayBlueLed);

    // -------------------------------------------------------------------------
    // 4) ĐIỀU KHIỂN HỒNG NGOẠI 38kHz (IR REMOTE 3D) & CHIẾT ÁP ĐỘ ẨM TRÊN BÀN MẠCH
    // -------------------------------------------------------------------------
    const remoteGrp = new THREE.Group();
    remoteGrp.position.set(-0.28, 0.745, 0.46);
    const remoteBody = new THREE.Mesh(
      new THREE.BoxGeometry(0.24, 0.035, 0.42),
      new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.3 })
    );
    remoteGrp.add(remoteBody);
    const remotePwrBtn = new THREE.Mesh(
      new THREE.CylinderGeometry(0.026, 0.026, 0.015, 12),
      new THREE.MeshBasicMaterial({ color: 0xef4444 })
    );
    remotePwrBtn.position.set(-0.05, 0.022, -0.14);
    remoteGrp.add(remotePwrBtn);
    for (let r = 0; r < 4; r++) {
      for (let c = 0; c < 3; c++) {
        const bKey = new THREE.Mesh(
          new THREE.CylinderGeometry(0.018, 0.018, 0.012, 10),
          new THREE.MeshStandardMaterial({ color: r === 0 ? 0x2563eb : 0x1e293b })
        );
        bKey.position.set(-0.06 + c * 0.06, 0.021, -0.05 + r * 0.065);
        remoteGrp.add(bKey);
      }
    }
    stationGroup.add(remoteGrp);

    // Chiết áp xoay (Potentiometer 3D màu xanh) đặt cạnh Remote trên bàn mạch
    const potBoard = new THREE.Mesh(
      new THREE.BoxGeometry(0.18, 0.03, 0.18),
      new THREE.MeshStandardMaterial({ color: 0x0284c7 })
    );
    potBoard.position.set(0.15, 0.74, 0.46);
    stationGroup.add(potBoard);
    const potKnob = new THREE.Mesh(
      new THREE.CylinderGeometry(0.055, 0.06, 0.06, 16),
      new THREE.MeshStandardMaterial({ color: 0xcbd5e1, metalness: 0.6 })
    );
    potKnob.position.set(0.15, 0.785, 0.46);
    stationGroup.add(potKnob);

    // -------------------------------------------------------------------------
    // 5) HỆ THỐNG DÂY CẮM JUMPER 3D (CHUẨN MÀU SẮC TỪ CHÂN ESP8266 -> BREADBOARD -> NGOẠI VI)
    // -------------------------------------------------------------------------
    // Dây Cam (+3.3V): ESP 3V3 -> Rãnh dương trên Breadboard
    addJumperWire3D([espX + 0.195, 0.78, espZ + 0.25], [bbX - 0.38, 0.78, bbZ - 0.27], 0xfb923c, 0.09);
    // Dây Đỏ (+5V VIN): ESP VIN -> Rãnh dương dưới Breadboard & sang Relay Đỏ
    addJumperWire3D([espX - 0.195, 0.78, espZ + 0.35], [bbX - 0.38, 0.78, bbZ + 0.25], 0xef4444, 0.12);
    addJumperWire3D([bbX + 0.38, 0.78, bbZ + 0.25], [0.6, 0.78, -0.24], 0xef4444, 0.09);
    // Dây Đen (GND): ESP GND -> Rãnh âm Breadboard
    addJumperWire3D([espX + 0.195, 0.78, espZ + 0.2], [bbX - 0.35, 0.78, bbZ - 0.23], 0x1e293b, 0.08);
    // Dây Vàng (D1 -> Servo Cửa chính & A0 -> Cảm biến đất YL-69)
    addJumperWire3D([espX + 0.195, 0.78, espZ - 0.3], [0.45, 0.85, -0.58], 0xfacc15, 0.16);
    addJumperWire3D([espX - 0.195, 0.78, espZ - 0.35], [0.15, 0.76, 0.46], 0xfacc15, 0.13);
    // Dây Xanh lá (D2 -> Đèn khách + Phát IR S8050; D7 -> Đèn ngủ)
    addJumperWire3D([espX + 0.195, 0.78, espZ - 0.25], [bbX - 0.39, 0.79, bbZ - 0.11], 0x22c55e, 0.11);
    addJumperWire3D([bbX - 0.22, 0.79, bbZ - 0.11], [bbX - 0.13, 0.79, bbZ - 0.11], 0xa855f7, 0.06);
    addJumperWire3D([espX + 0.195, 0.78, espZ + 0.05], [bbX + 0.16, 0.79, bbZ - 0.11], 0x22c55e, 0.13);
    // Dây Tím (D5 -> Mắt thu IR VS1838B)
    addJumperWire3D([espX + 0.195, 0.78, espZ - 0.05], [bbX - 0.26, 0.79, bbZ + 0.11], 0xc084fc, 0.11);
    // Dây Xanh dương (D3 -> Relay Đỏ + Diode 1N4007 + Máy bơm; D6 -> DHT11 & Relay Xanh)
    addJumperWire3D([espX + 0.195, 0.78, espZ - 0.2], [0.6, 0.78, -0.28], 0x38bdf8, 0.15);
    addJumperWire3D([espX + 0.195, 0.78, espZ], [bbX + 0.02, 0.79, bbZ + 0.11], 0x38bdf8, 0.12);
    addJumperWire3D([bbX + 0.06, 0.79, bbZ + 0.11], [0.6, 0.78, 0.18], 0x38bdf8, 0.1);
    // Dây Hồng (D8 -> Còi Buzzer 5V)
    addJumperWire3D([espX + 0.195, 0.78, espZ + 0.1], [bbX + 0.28, 0.79, bbZ + 0.11], 0xf43f5e, 0.12);

    scene.add(stationGroup);
  }

  function buildFloatingPins() {
    if (!labelsContainer) return;
    labelsContainer.innerHTML = "";
    PIN_META.forEach((m) => {
      pinAnchors[m.id] = new THREE.Vector3(m.pos[0], m.pos[1], m.pos[2]);
      const el = document.createElement("button");
      if (m.kind === "sensor") {
        el.className = "pin-3d on";
        el.style.borderColor = "#38bdf8";
        el.style.background = "rgba(15, 23, 42, 0.88)";
        el.title = "Bấm để chuyển góc nhìn Camera cận cảnh tới linh kiện này";
        let initVal = "ONLINE";
        if (m.id === "sensor_soil_a0") initVal = `${sensorState.soil_moisture_pct}%`;
        else if (m.id === "sensor_dht11_d6") initVal = `${sensorState.temp_c}°C | ${sensorState.humidity_pct}%`;
        else if (m.id === "sensor_ir_d5") initVal = "38kHz READY";
        else if (m.id === "board_esp8266") initVal = "9 GPIO OK";
        el.innerHTML = `<span class="pin-icon">${m.icon}</span> <span class="pin-name">${m.shortName}:</span> <strong class="pin-state" style="color:#38bdf8;">${initVal}</strong>`;
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          if (m.cam) setCameraView(m.cam);
        });
      } else {
        el.className = "pin-3d off";
        el.title = "Bấm để Bật/Tắt hoặc Đóng/Mở trực tiếp thiết bị này";
        el.innerHTML = `<span class="pin-icon">${m.icon}</span> <span class="pin-name">${m.shortName}:</span> <strong class="pin-state">OFF</strong>`;
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

  function updatePinPositions() {
    if (!labelsContainer || !renderer) return;
    const w = container.clientWidth;
    const h = container.clientHeight;
    PIN_META.forEach((m) => {
      const el = pinElements[m.id];
      if (!el) return;
      const v = pinAnchors[m.id].clone().project(camera);
      if (v.z > 1) {
        el.style.display = "none";
        return;
      }
      el.style.display = "inline-flex";
      const x = (v.x * 0.5 + 0.5) * w;
      const y = (-(v.y * 0.5) + 0.5) * h;
      el.style.transform = `translate(-50%, -50%) translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    });
  }

  function bindMouseControls() {
    const dom = renderer.domElement;
    dom.addEventListener("mousedown", (e) => {
      isDragging = true;
      camGoal.autoRotate = false;
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

    window.addEventListener("mouseup", () => {
      isDragging = false;
    });

    dom.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        camGoal.radius = Math.max(5.2, Math.min(22.0, camGoal.radius + e.deltaY * 0.008));
      },
      { passive: false }
    );
  }

  function setCameraView(preset) {
    camGoal.autoRotate = false;
    if (preset === "overview") {
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
      Object.assign(camGoal, { theta: 0.22, phi: 0.96, radius: 5.4, targetX: -4.2, targetY: 0.78, targetZ: 4.35 });
    } else if (preset === "rotate") {
      camGoal.autoRotate = !camState.autoRotate;
      camState.autoRotate = camGoal.autoRotate;
    }
  }

  function triggerIr38kHzVisualBlast() {
    irBlastTimer = 45; // ~0.75 giây bắn sóng hồng ngoại 38kHz từ D2 lên Điều hòa
  }

  function updateSensors(mqttSummary, serverConnected = true) {
    if (!mqttSummary) return;
    const soil = mqttSummary.soil_moisture_telemetry || {};
    const dht = mqttSummary.dht11_telemetry || {};
    const espStat = mqttSummary.esp8266_status || {};
    const isOnline = serverConnected !== undefined ? Boolean(serverConnected) : (espStat.online !== false);

    const pinBoard = pinElements["board_esp8266"];
    if (pinBoard) {
      const st = pinBoard.querySelector(".pin-state");
      if (st) {
        st.textContent = isOnline ? "SERVER ONLINE" : "OFFLINE (MẶC ĐỊNH)";
        st.style.color = isOnline ? "#38bdf8" : "#fb923c";
      }
      pinBoard.style.borderColor = isOnline ? "#38bdf8" : "#f59e0b";
    }
    if (boardLedMats.esp_onboard) {
      boardLedMats.esp_onboard.color.setHex(isOnline ? 0x38bdf8 : 0xf59e0b);
    }

    if (soil.soil_moisture_pct !== undefined) {
      sensorState.soil_moisture_pct = Math.round(Number(soil.soil_moisture_pct));
      sensorState.soil_status = soil.status_label || (sensorState.soil_moisture_pct < 40 ? "Khô" : "Đủ ẩm");
      const pinSoil = pinElements["sensor_soil_a0"];
      if (pinSoil) {
        const st = pinSoil.querySelector(".pin-state");
        if (st) {
          st.textContent = `${sensorState.soil_moisture_pct}% (${sensorState.soil_status})`;
          st.style.color = sensorState.soil_moisture_pct < 40 ? "#fb923c" : "#4ade80";
        }
      }
      if (lm393AlertLedMat) {
        lm393AlertLedMat.color.setHex(sensorState.soil_moisture_pct < 40 ? 0xef4444 : 0x22c55e);
      }
      if (gardenSoilMat && !deviceStates.garden_pump) {
        gardenSoilMat.color.setHex(sensorState.soil_moisture_pct < 40 ? 0x78350f : 0x3b1704);
      }
    }

    if (dht.temp_c !== undefined) {
      sensorState.temp_c = Number(dht.temp_c).toFixed(1);
      sensorState.humidity_pct = Math.round(Number(dht.humidity_pct || 65));
      const pinDht = pinElements["sensor_dht11_d6"];
      if (pinDht) {
        const st = pinDht.querySelector(".pin-state");
        if (st) {
          st.textContent = `${sensorState.temp_c}°C | ${sensorState.humidity_pct}%`;
          st.style.color = Number(dht.temp_c) > 31 ? "#f87171" : "#38bdf8";
        }
      }
    }
  }

  function updateDevices(devicesArray, mqttSummary, serverConnected = true) {
    const isOnline = serverConnected !== undefined ? Boolean(serverConnected) : true;
    (devicesArray || []).forEach((d) => {
      const isActive = d.state === "ON" || d.state === "OPEN";
      if (d.id === "ac" && isActive !== prevAcState) {
        prevAcState = isActive;
        triggerIr38kHzVisualBlast();
      }
      deviceStates[d.id] = isActive;

      const pin = pinElements[d.id];
      if (pin) {
        const isLockedOffline = !isOnline && (d.id === "main_door" || d.id === "alarm_siren");
        pin.className = `pin-3d ${isActive ? "on" : "off"}`;
        pin.style.borderColor = isLockedOffline ? "#f59e0b" : "";
        const stSpan = pin.querySelector(".pin-state");
        if (stSpan) {
          stSpan.textContent = isLockedOffline ? "🔒 KHÓA OFFLINE" : d.state;
          stSpan.style.color = isLockedOffline ? "#fbbf24" : "";
        }
      }
    });

    if (mqttSummary) {
      updateSensors(mqttSummary, isOnline);
    }

    // 1. Đèn phòng khách (Chân D2)
    if (deviceStates.living_room_light) {
      livingBulbMat.color.setHex(0xfffbeb);
      livingBulbMat.emissive.setHex(0xfbbf24);
      livingBulbMat.emissiveIntensity = 1.6;
      livingPointLight.intensity = 2.5;
      if (boardLedMats.d2_living) boardLedMats.d2_living.color.setHex(0xef4444);
    } else {
      livingBulbMat.color.setHex(0x475569);
      livingBulbMat.emissive.setHex(0x000000);
      livingBulbMat.emissiveIntensity = 0;
      livingPointLight.intensity = 0;
      if (boardLedMats.d2_living) boardLedMats.d2_living.color.setHex(0x450a0a);
    }

    // 2. Đèn phòng ngủ (Chân D7)
    if (deviceStates.bedroom_light) {
      bedBulbMat.color.setHex(0xfffbeb);
      bedBulbMat.emissive.setHex(0xffb703);
      bedBulbMat.emissiveIntensity = 1.5;
      bedLampShadeMat.emissive.setHex(0xf59e0b);
      bedLampShadeMat.emissiveIntensity = 1.1;
      bedPointLight.intensity = 2.2;
      if (boardLedMats.d7_bed) boardLedMats.d7_bed.color.setHex(0xfacc15);
    } else {
      bedBulbMat.color.setHex(0x475569);
      bedBulbMat.emissive.setHex(0x000000);
      bedBulbMat.emissiveIntensity = 0;
      bedLampShadeMat.emissive.setHex(0x000000);
      bedLampShadeMat.emissiveIntensity = 0;
      bedPointLight.intensity = 0;
      if (boardLedMats.d7_bed) boardLedMats.d7_bed.color.setHex(0x422006);
    }

    // 3. Cửa chính & Servo SG90 (Chân D1)
    if (deviceStates.main_door) {
      doorLockLedMat.color.setHex(0x22c55e);
      doorEntranceLight.intensity = 1.6;
    } else {
      doorLockLedMat.color.setHex(0xef4444);
      doorEntranceLight.intensity = 0;
    }

    // 4. Quạt trần & Relay Xanh (Chân D6)
    if (deviceStates.fan) {
      fanRingMat.color.setHex(0x00f5d4);
      if (boardLedMats.d6_relay_blue) boardLedMats.d6_relay_blue.color.setHex(0x22c55e);
    } else {
      fanRingMat.color.setHex(0x334155);
      if (boardLedMats.d6_relay_blue) boardLedMats.d6_relay_blue.color.setHex(0x172554);
    }

    // 5. Điều hòa & Phát IR 38kHz (Chân D2)
    if (deviceStates.ac) {
      acLedMat.color.setHex(0x38bdf8);
      acParticles.visible = true;
      acCoolLight.intensity = 1.4;
      if (boardLedMats.d2_ir) boardLedMats.d2_ir.color.setHex(0xd946ef);
    } else {
      acLedMat.color.setHex(0x334155);
      acParticles.visible = false;
      acCoolLight.intensity = 0;
      if (boardLedMats.d2_ir) boardLedMats.d2_ir.color.setHex(0x581c87);
    }

    // 6. Còi báo động Buzzer 5V (Chân D8)
    if (!deviceStates.alarm_siren) {
      sirenBulbMat.emissive.setHex(0x000000);
      sirenBulbMat.emissiveIntensity = 0;
      sirenPointLight.intensity = 0;
      if (boardLedMats.d8_buzzer) boardLedMats.d8_buzzer.color.setHex(0x1f2937);
    } else {
      if (boardLedMats.d8_buzzer) boardLedMats.d8_buzzer.color.setHex(0xef4444);
    }

    // 7. Máy bơm nước mini 5V & Relay Đỏ (Chân D3)
    if (deviceStates.garden_pump) {
      if (pumpBodyMat) {
        pumpBodyMat.emissive.setHex(0x0ea5e9);
        pumpBodyMat.emissiveIntensity = 0.85;
      }
      if (pumpWaterParticles) pumpWaterParticles.visible = true;
      if (pumpPointLight) pumpPointLight.intensity = 1.6;
      if (gardenSoilMat) gardenSoilMat.color.setHex(0x271002); // Đất ướt đậm màu khi đang tưới
      if (boardLedMats.d3_relay_red) boardLedMats.d3_relay_red.color.setHex(0xef4444);
    } else {
      if (pumpBodyMat) {
        pumpBodyMat.emissive.setHex(0x000000);
        pumpBodyMat.emissiveIntensity = 0;
      }
      if (pumpWaterParticles) pumpWaterParticles.visible = false;
      if (pumpPointLight) pumpPointLight.intensity = 0;
      if (boardLedMats.d3_relay_red) boardLedMats.d3_relay_red.color.setHex(0x450a0a);
    }
  }

  function animate(timeMs) {
    requestAnimationFrame(animate);

    // 1. Nội suy góc xoay Cửa Chính & Tay đòn Động cơ Servo SG90 (Chân D1)
    const targetDoorAngle = deviceStates.main_door ? -1.62 : 0.0;
    currentDoorAngle += (targetDoorAngle - currentDoorAngle) * 0.12;
    if (doorPivot) {
      doorPivot.rotation.y = currentDoorAngle;
    }
    if (servoHornPivot) {
      servoHornPivot.rotation.y = currentDoorAngle;
    }

    // 2. Nội suy tốc độ Quạt Trần (Chân D6)
    const targetFanSpeed = deviceStates.fan ? 0.24 : 0.0;
    fanSpeed += (targetFanSpeed - fanSpeed) * 0.06;
    if (fanBladesGroup && fanSpeed > 0.001) {
      fanBladesGroup.rotation.y += fanSpeed;
    }

    // 3. Cánh đảo gió & Hạt sương lạnh Điều Hòa (Chân D2 IR)
    if (acFlapPivot) {
      const targetFlap = deviceStates.ac ? 0.65 : 0.0;
      acFlapPivot.rotation.x += (targetFlap - acFlapPivot.rotation.x) * 0.1;
    }
    if (acParticles && deviceStates.ac) {
      const posArr = acParticles.geometry.attributes.position.array;
      for (let i = 0; i < posArr.length; i += 3) {
        posArr[i + 1] -= 0.025;
        posArr[i + 2] += 0.038;
        if (posArr[i + 1] < 0.4 || posArr[i + 2] > -0.6) {
          posArr[i] = -3.2 + (Math.random() - 0.5) * 1.6;
          posArr[i + 1] = 2.42;
          posArr[i + 2] = -3.15;
        }
      }
      acParticles.geometry.attributes.position.needsUpdate = true;
    }

    // 4. Đèn chớp Còi Báo Động Buzzer 5V (Chân D8)
    if (deviceStates.alarm_siren) {
      const pulse = (Math.sin(timeMs * 0.018) + 1) * 0.5;
      sirenBulbMat.emissive.setHex(0xef4444);
      sirenBulbMat.emissiveIntensity = 0.6 + pulse * 2.2;
      sirenPointLight.intensity = pulse * 3.5;
    }

    // 5. Máy bơm nước mini 5V & Hạt tia nước phun tưới cây 3D (Chân D3)
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

    // 6. Vòng sóng Tia Hồng ngoại 38kHz 3D bắn từ Bàn trà lên Điều hòa
    if (irBlastTimer > 0) {
      irBlastTimer--;
      irBeamRings.forEach((r) => {
        r.mesh.visible = true;
        r.phase = (r.phase + 0.045) % 1.0;
        const t = r.phase;
        r.mesh.position.set(
          -2.46 + (-3.2 - -2.46) * t,
          0.6 + (2.62 - 0.6) * t,
          -0.8 + (-3.18 - -0.8) * t
        );
        r.mesh.lookAt(-3.2, 2.62, -3.18);
        const s = 0.6 + t * 2.2;
        r.mesh.scale.set(s, s, s);
        r.mat.opacity = (1.0 - t) * 0.9;
      });
    } else {
      irBeamRings.forEach((r) => {
        if (r.mesh.visible) r.mesh.visible = false;
      });
    }

    // 7. Cập nhật Camera mượt mà
    if (camGoal.autoRotate) {
      camGoal.theta += 0.0035;
    }
    camState.theta += (camGoal.theta - camState.theta) * 0.12;
    camState.phi += (camGoal.phi - camState.phi) * 0.12;
    camState.radius += (camGoal.radius - camState.radius) * 0.12;
    camState.targetX += (camGoal.targetX - camState.targetX) * 0.12;
    camState.targetY += (camGoal.targetY - camState.targetY) * 0.12;
    camState.targetZ += (camGoal.targetZ - camState.targetZ) * 0.12;

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
    renderer.setSize(w, h);
  }

  return {
    init,
    updateDevices,
    updateSensors,
    triggerIr38kHzVisualBlast,
    setCameraView,
    onResize,
  };
})();
