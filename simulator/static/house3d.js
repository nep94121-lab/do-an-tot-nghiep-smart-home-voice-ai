"use strict";

/**
 * Mô hình Ngôi Nhà Thông Minh 3D (Interactive 3D Smart Home Digital Twin)
 * Xây dựng bằng Three.js (WebGL) — Phản hồi tức thì với 6 thiết bị từ Gemini 3.8 Live:
 *  1. main_door         : Cánh cửa chính xoay mở/đóng 95° quanh bản lề + chốt LED xanh/đỏ
 *  2. living_room_light : Đèn chùm phòng khách + PointLight chiếu sáng nội thất Sofa/Bàn
 *  3. bedroom_light     : Đèn trần & đèn ngủ đầu giường + PointLight chiếu sáng Phòng ngủ
 *  4. fan               : Quạt trần 4 cánh quay có quán tính (tăng/giảm tốc mượt)
 *  5. ac                : Điều hòa mở cánh đảo gió + luồng hạt khí lạnh 3D (Particle System)
 *  6. alarm_siren       : Đèn còi báo động chớp đỏ khẩn cấp toàn ngôi nhà
 */
window.SmartHome3D = (() => {
  let container, labelsContainer;
  let scene, camera, renderer;
  let onDeviceClickCallback = null;

  // Điều khiển góc nhìn Camera (Orbit thủ công mượt mà không cần file phụ)
  let camState = {
    theta: 0.46,       // góc ngang (rad)
    phi: 1.04,         // góc dọc (rad)
    radius: 13.8,      // khoảng cách
    targetX: 0,
    targetY: 1.05,
    targetZ: 0.2,
    autoRotate: false,
  };
  let camGoal = { ...camState };
  let isDragging = false;
  let prevMouse = { x: 0, y: 0 };

  // Trạng thái mục tiêu của 6 thiết bị
  const deviceStates = {
    main_door: false,         // true = OPEN
    living_room_light: false, // true = ON
    bedroom_light: false,     // true = ON
    fan: false,               // true = ON
    ac: false,                // true = ON
    alarm_siren: false,       // true = ON
  };

  // Các đối tượng 3D cần diễn hoạt (animate)
  let doorPivot = null;
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

  let sirenBulbMat = null;
  let sirenPointLight = null;

  // Điểm neo 3D để gắn nhãn nổi HTML (Floating 3D Pins)
  const pinAnchors = {};
  const pinElements = {};

  const PIN_META = [
    { id: "main_door", icon: "🚪", shortName: "Cửa chính", pos: [-1.8, 2.35, 3.65] },
    { id: "living_room_light", icon: "💡", shortName: "Đèn khách", pos: [-2.6, 3.15, -0.2] },
    { id: "fan", icon: "🌀", shortName: "Quạt trần", pos: [-2.6, 3.35, -1.8] },
    { id: "ac", icon: "❄️", shortName: "Điều hòa", pos: [-3.2, 2.75, -3.35] },
    { id: "bedroom_light", icon: "🛏️", shortName: "Đèn ngủ", pos: [2.7, 3.1, -0.3] },
    { id: "alarm_siren", icon: "🚨", shortName: "Còi báo động", pos: [-0.4, 3.05, 3.65] },
  ];

  function init(canvasContainerId, overlayLabelsId, onToggleDevice) {
    container = document.getElementById(canvasContainerId);
    labelsContainer = document.getElementById(overlayLabelsId);
    onDeviceClickCallback = onToggleDevice;
    if (!container || !window.THREE) return;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x080d1a);
    scene.fog = new THREE.FogExp2(0x080d1a, 0.022);

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
    buildFloatingPins();
    bindMouseControls();

    window.addEventListener("resize", onResize);
    requestAnimationFrame(animate);
  }

  function buildLighting() {
    const hemi = new THREE.HemisphereLight(0x8ecae6, 0x1e293b, 0.42);
    scene.add(hemi);

    const moonDir = new THREE.DirectionalLight(0x94a3b8, 0.38);
    moonDir.position.set(8, 14, 10);
    moonDir.castShadow = true;
    moonDir.shadow.mapSize.width = 1024;
    moonDir.shadow.mapSize.height = 1024;
    scene.add(moonDir);
  }

  function buildHouseArchitecture() {
    // Mặt đất sân vườn bên ngoài
    const groundGeo = new THREE.PlaneGeometry(28, 24);
    const groundMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.95 });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.12;
    ground.receiveShadow = true;
    scene.add(ground);

    // Lưới nền kỹ thuật số (Digital Twin Grid)
    const grid = new THREE.GridHelper(24, 24, 0x1e3a5f, 0x132038);
    grid.position.y = -0.11;
    scene.add(grid);

    // Đế móng ngôi nhà
    const baseGeo = new THREE.BoxGeometry(11.4, 0.16, 7.6);
    const baseMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.7 });
    const base = new THREE.Mesh(baseGeo, baseMat);
    base.position.set(0, -0.04, 0);
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
    const porchGeo = new THREE.BoxGeometry(2.6, 0.1, 1.4);
    const porchMat = new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.8 });
    const porch = new THREE.Mesh(porchGeo, porchMat);
    porch.position.set(-1.8, -0.05, 4.3);
    porch.receiveShadow = true;
    scene.add(porch);

    // Vật liệu tường
    const wallMat = new THREE.MeshStandardMaterial({ color: 0xcbd5e1, roughness: 0.75 });
    const wallTrimMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.5 });

    // Tường sau (Back Wall)
    const backWall = new THREE.Mesh(new THREE.BoxGeometry(11.2, 3.4, 0.2), wallMat);
    backWall.position.set(0, 1.7, -3.6);
    backWall.castShadow = true;
    backWall.receiveShadow = true;
    scene.add(backWall);

    // Tường trái (Left Wall)
    const leftWall = new THREE.Mesh(new THREE.BoxGeometry(0.2, 3.4, 7.4), wallMat);
    leftWall.position.set(-5.5, 1.7, 0);
    leftWall.castShadow = true;
    leftWall.receiveShadow = true;
    scene.add(leftWall);

    // Tường phải (Right Wall - thấp một nửa phía trước để dễ nhìn phòng ngủ)
    const rightWallBack = new THREE.Mesh(new THREE.BoxGeometry(0.2, 3.4, 4.2), wallMat);
    rightWallBack.position.set(5.5, 1.7, -1.6);
    scene.add(rightWallBack);

    const rightWallFrontLow = new THREE.Mesh(new THREE.BoxGeometry(0.2, 1.1, 3.2), wallMat);
    rightWallFrontLow.position.set(5.5, 0.55, 2.1);
    scene.add(rightWallFrontLow);

    // Vách ngăn giữa Phòng Khách & Phòng Ngủ (có lối đi ở giữa)
    const midWallBack = new THREE.Mesh(new THREE.BoxGeometry(0.18, 3.4, 3.2), wallMat);
    midWallBack.position.set(0.3, 1.7, -2.0);
    midWallBack.castShadow = true;
    midWallBack.receiveShadow = true;
    scene.add(midWallBack);

    const midWallFront = new THREE.Mesh(new THREE.BoxGeometry(0.18, 1.3, 2.3), wallMat);
    midWallFront.position.set(0.3, 0.65, 2.45);
    scene.add(midWallFront);

    // Tường mặt tiền xung quanh Cửa Chính (Cutaway để nhìn rõ vào trong)
    // Trụ trái cửa chính
    const frontLeftPillar = new THREE.Mesh(new THREE.BoxGeometry(2.6, 2.7, 0.22), wallMat);
    frontLeftPillar.position.set(-4.2, 1.35, 3.6);
    scene.add(frontLeftPillar);

    // Trụ phải cửa chính
    const frontRightPillar = new THREE.Mesh(new THREE.BoxGeometry(1.4, 2.7, 0.22), wallMat);
    frontRightPillar.position.set(-0.3, 1.35, 3.6);
    scene.add(frontRightPillar);

    // Dầm ngang trên cửa chính
    const frontHeader = new THREE.Mesh(new THREE.BoxGeometry(4.8, 0.5, 0.24), wallTrimMat);
    frontHeader.position.set(-2.2, 2.95, 3.6);
    scene.add(frontHeader);

    // Dầm trần treo Đèn & Quạt (Ceiling Beams)
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

    // 4. Giường ngủ (Phòng ngủ bên phải)
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

    // Tủ đầu giường (Nightstand)
    const nightStand = new THREE.Mesh(new THREE.BoxGeometry(0.65, 0.58, 0.58), woodMat);
    nightStand.position.set(1.25, 0.34, -2.8);
    scene.add(nightStand);
  }

  function buildSmartDevices() {
    // =========================================================================
    // 1. CỬA CHÍNH (main_door) — Xoay quanh bản lề trái tại (-2.9, 0, 3.6)
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

    // Ô kính mờ trên cánh cửa
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

    // Tay nắm khóa thông minh Smart Lock
    const handle = new THREE.Mesh(
      new THREE.BoxGeometry(0.18, 0.42, 0.2),
      new THREE.MeshStandardMaterial({ color: 0xfacc15, metalness: 0.8, roughness: 0.2 })
    );
    handle.position.set(1.55, 1.25, 0);
    doorPivot.add(handle);

    scene.add(doorPivot);

    // Đèn báo trạng thái khóa cửa trên khung
    doorLockLedMat = new THREE.MeshBasicMaterial({ color: 0xef4444 });
    const lockLed = new THREE.Mesh(new THREE.SphereGeometry(0.11, 16, 16), doorLockLedMat);
    lockLed.position.set(-0.85, 1.6, 3.74);
    scene.add(lockLed);

    doorEntranceLight = new THREE.PointLight(0x4ade80, 0, 5.5);
    doorEntranceLight.position.set(-1.9, 2.4, 3.2);
    scene.add(doorEntranceLight);

    // =========================================================================
    // 2. ĐÈN PHÒNG KHÁCH (living_room_light)
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
    // 3. QUẠT TRẦN 4 CÁNH (fan)
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
    // 4. ĐIỀU HÒA NHIỆT ĐỘ (ac) + LUỒNG HẠT GIÓ LẠNH 3D
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

    // Hạt gió lạnh 3D (Particle System)
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
    // 5. ĐÈN PHÒNG NGỦ (bedroom_light) — Đèn trần + Đèn ngủ đầu giường
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
    // 6. CÒI & ĐÈN BÁO ĐỘNG (alarm_siren)
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

    sirenPointLight = new THREE.PointLight(0xef4444, 0, 14);
    sirenPointLight.position.set(-0.4, 2.85, 4.1);
    scene.add(sirenPointLight);
  }

  function buildFloatingPins() {
    if (!labelsContainer) return;
    labelsContainer.innerHTML = "";
    PIN_META.forEach((m) => {
      pinAnchors[m.id] = new THREE.Vector3(m.pos[0], m.pos[1], m.pos[2]);
      const el = document.createElement("button");
      el.className = "pin-3d off";
      el.title = "Bấm để Bật/Tắt hoặc Đóng/Mở trực tiếp thiết bị này";
      el.innerHTML = `<span class="pin-icon">${m.icon}</span> <span class="pin-name">${m.shortName}:</span> <strong class="pin-state">OFF</strong>`;
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        if (onDeviceClickCallback) {
          onDeviceClickCallback(m.id);
        }
      });
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
        camGoal.radius = Math.max(6.5, Math.min(22.0, camGoal.radius + e.deltaY * 0.008));
      },
      { passive: false }
    );
  }

  function setCameraView(preset) {
    camGoal.autoRotate = false;
    if (preset === "overview") {
      Object.assign(camGoal, { theta: 0.48, phi: 0.92, radius: 14.2, targetX: 0, targetY: 1.1, targetZ: 0.3 });
    } else if (preset === "living") {
      Object.assign(camGoal, { theta: 0.25, phi: 1.02, radius: 8.8, targetX: -2.5, targetY: 1.3, targetZ: -0.8 });
    } else if (preset === "bedroom") {
      Object.assign(camGoal, { theta: -0.35, phi: 0.98, radius: 9.0, targetX: 2.8, targetY: 1.2, targetZ: -1.1 });
    } else if (preset === "door") {
      Object.assign(camGoal, { theta: 0.12, phi: 1.15, radius: 7.2, targetX: -1.9, targetY: 1.3, targetZ: 3.2 });
    } else if (preset === "rotate") {
      camGoal.autoRotate = !camState.autoRotate;
      camState.autoRotate = camGoal.autoRotate;
    }
  }

  function updateDevices(devicesArray) {
    (devicesArray || []).forEach((d) => {
      const isActive = d.state === "ON" || d.state === "OPEN";
      deviceStates[d.id] = isActive;

      const pin = pinElements[d.id];
      if (pin) {
        pin.className = `pin-3d ${isActive ? "on" : "off"}`;
        const stSpan = pin.querySelector(".pin-state");
        if (stSpan) stSpan.textContent = d.state;
      }
    });

    // Cập nhật ánh sáng & vật liệu tức thì
    // 1. Đèn phòng khách
    if (deviceStates.living_room_light) {
      livingBulbMat.color.setHex(0xfffbeb);
      livingBulbMat.emissive.setHex(0xfbbf24);
      livingBulbMat.emissiveIntensity = 1.6;
      livingPointLight.intensity = 2.5;
    } else {
      livingBulbMat.color.setHex(0x475569);
      livingBulbMat.emissive.setHex(0x000000);
      livingBulbMat.emissiveIntensity = 0;
      livingPointLight.intensity = 0;
    }

    // 2. Đèn phòng ngủ
    if (deviceStates.bedroom_light) {
      bedBulbMat.color.setHex(0xfffbeb);
      bedBulbMat.emissive.setHex(0xffb703);
      bedBulbMat.emissiveIntensity = 1.5;
      bedLampShadeMat.emissive.setHex(0xf59e0b);
      bedLampShadeMat.emissiveIntensity = 1.1;
      bedPointLight.intensity = 2.2;
    } else {
      bedBulbMat.color.setHex(0x475569);
      bedBulbMat.emissive.setHex(0x000000);
      bedBulbMat.emissiveIntensity = 0;
      bedLampShadeMat.emissive.setHex(0x000000);
      bedLampShadeMat.emissiveIntensity = 0;
      bedPointLight.intensity = 0;
    }

    // 3. Cửa chính LED
    if (deviceStates.main_door) {
      doorLockLedMat.color.setHex(0x22c55e);
      doorEntranceLight.intensity = 1.6;
    } else {
      doorLockLedMat.color.setHex(0xef4444);
      doorEntranceLight.intensity = 0;
    }

    // 4. Quạt trần LED
    if (deviceStates.fan) {
      fanRingMat.color.setHex(0x00f5d4);
    } else {
      fanRingMat.color.setHex(0x334155);
    }

    // 5. Điều hòa
    if (deviceStates.ac) {
      acLedMat.color.setHex(0x38bdf8);
      acParticles.visible = true;
      acCoolLight.intensity = 1.4;
    } else {
      acLedMat.color.setHex(0x334155);
      acParticles.visible = false;
      acCoolLight.intensity = 0;
    }

    // 6. Còi báo động
    if (!deviceStates.alarm_siren) {
      sirenBulbMat.emissive.setHex(0x000000);
      sirenBulbMat.emissiveIntensity = 0;
      sirenPointLight.intensity = 0;
    }
  }

  function animate(timeMs) {
    requestAnimationFrame(animate);

    // 1. Nội suy góc xoay Cửa Chính (Mở = -1.62 rad ~ 93 độ)
    const targetDoorAngle = deviceStates.main_door ? -1.62 : 0.0;
    currentDoorAngle += (targetDoorAngle - currentDoorAngle) * 0.12;
    if (doorPivot) {
      doorPivot.rotation.y = currentDoorAngle;
    }

    // 2. Nội suy tốc độ Quạt Trần
    const targetFanSpeed = deviceStates.fan ? 0.24 : 0.0;
    fanSpeed += (targetFanSpeed - fanSpeed) * 0.06;
    if (fanBladesGroup && fanSpeed > 0.001) {
      fanBladesGroup.rotation.y += fanSpeed;
    }

    // 3. Cánh đảo gió & Hạt sương lạnh Điều Hòa
    if (acFlapPivot) {
      const targetFlap = deviceStates.ac ? 0.65 : 0.0;
      acFlapPivot.rotation.x += (targetFlap - acFlapPivot.rotation.x) * 0.1;
    }
    if (acParticles && deviceStates.ac) {
      const posArr = acParticles.geometry.attributes.position.array;
      for (let i = 0; i < posArr.length; i += 3) {
        posArr[i + 1] -= 0.025; // rơi nhẹ xuống
        posArr[i + 2] += 0.038; // thổi ra phía sofa
        if (posArr[i + 1] < 0.4 || posArr[i + 2] > -0.6) {
          posArr[i] = -3.2 + (Math.random() - 0.5) * 1.6;
          posArr[i + 1] = 2.42;
          posArr[i + 2] = -3.15;
        }
      }
      acParticles.geometry.attributes.position.needsUpdate = true;
    }

    // 4. Đèn chớp Còi Báo Động
    if (deviceStates.alarm_siren) {
      const pulse = (Math.sin(timeMs * 0.018) + 1) * 0.5;
      sirenBulbMat.emissive.setHex(0xef4444);
      sirenBulbMat.emissiveIntensity = 0.6 + pulse * 2.2;
      sirenPointLight.intensity = pulse * 3.5;
    }

    // 5. Cập nhật Camera mượt mà
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
    setCameraView,
    onResize,
  };
})();
