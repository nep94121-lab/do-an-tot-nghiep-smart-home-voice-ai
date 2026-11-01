"""Script Blender 5.2 (bpy) tạo mô hình 3D Biệt thự Thông minh (Smart Home Villa)
Xuất ra định dạng chuẩn glTF 2.0 (.glb): simulator/static/models/smarthome_villa.glb
Tọa độ khớp 1:1 với hệ trục của Three.js trong simulator/static/house3d.js.
Lưu ý: Blender dùng hệ trục Z-up, khi export glTF (+Y up) Blender tự động chuyển:
  Blender (X, Y, Z) -> Three.js (X, Z_blender, -Y_blender)
Để tránh nhầm lẫn hệ trục, ta đặt hàm tiện ích `to_blender_pos(tx, ty, tz)` chuyển từ
tọa độ Three.js `(tx, ty, tz)` sang tọa độ Blender `(tx, -tz, ty)`!
"""

import math
import pathlib
import bpy
import bmesh


def to_bpos(tx: float, ty: float, tz: float) -> tuple[float, float, float]:
    """Chuyển tọa độ Three.js (X, Y_up, Z_front) sang Blender (X, Y_depth, Z_up)."""
    return (float(tx), float(-tz), float(ty))


def to_bscale(sx: float, sy: float, sz: float) -> tuple[float, float, float]:
    """Chuyển kích thước Three.js (W_x, H_y, D_z) sang kích thước hộp chuẩn trong Blender."""
    return (float(sx), float(sz), float(sy))


def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_pbr_mat(
    name: str,
    rgba: tuple[float, float, float, float],
    roughness: float = 0.5,
    metallic: float = 0.0,
    emission_rgb: tuple[float, float, float] | None = None,
    emission_strength: float = 0.0,
    alpha: float = 1.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if alpha < 1.0:
            bsdf.inputs["Alpha"].default_value = alpha
            if hasattr(mat, "blend_method"):
                mat.blend_method = "BLEND"
        if emission_rgb and emission_strength > 0:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = (*emission_rgb, 1.0)
            elif "Emission" in bsdf.inputs:
                bsdf.inputs["Emission"].default_value = (*emission_rgb, 1.0)
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def add_beveled_box(
    name: str,
    tx: float,
    ty: float,
    tz: float,
    sx: float,
    sy: float,
    sz: float,
    mat: bpy.types.Material,
    bevel_width: float = 0.02,
    bevel_segments: int = 2,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=to_bpos(tx, ty, tz))
    obj = bpy.context.active_object
    obj.name = name
    bx, by, bz = to_bscale(sx, sy, sz)
    obj.scale = (bx, by, bz)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    if bevel_width > 0:
        bev = obj.modifiers.new(name="Bevel", type="BEVEL")
        bev.width = bevel_width
        bev.segments = bevel_segments
        bev.limit_method = "ANGLE"
        bpy.ops.object.modifier_apply(modifier=bev.name)

    bpy.ops.object.shade_smooth()
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    return obj


def add_cylinder_3d(
    name: str,
    tx: float,
    ty: float,
    tz: float,
    radius: float,
    height: float,
    mat: bpy.types.Material,
    vertices: int = 24,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=height,
        location=to_bpos(tx, ty, tz),
    )
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.shade_smooth()
    obj.data.materials.append(mat)
    return obj


def add_uv_sphere(
    name: str,
    tx: float,
    ty: float,
    tz: float,
    radius: float,
    mat: bpy.types.Material,
    scale_xyz: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24,
        ring_count=16,
        radius=radius,
        location=to_bpos(tx, ty, tz),
    )
    obj = bpy.context.active_object
    obj.name = name
    bx, by, bz = to_bscale(*scale_xyz)
    obj.scale = (bx, by, bz)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.shade_smooth()
    obj.data.materials.append(mat)
    return obj


def build_villa() -> None:
    clear_scene()

    # Bảng vật liệu PBR cao cấp
    mat_foundation = make_pbr_mat("GraniteFoundation", (0.16, 0.20, 0.27, 1.0), roughness=0.55, metallic=0.1)
    mat_deck_trim = make_pbr_mat("DeckTrim", (0.09, 0.13, 0.20, 1.0), roughness=0.4, metallic=0.3)
    mat_oak_floor = make_pbr_mat("OakFloorLiving", (0.42, 0.28, 0.17, 1.0), roughness=0.38, metallic=0.02)
    mat_walnut_floor = make_pbr_mat("WalnutFloorBed", (0.30, 0.20, 0.14, 1.0), roughness=0.42, metallic=0.02)
    mat_porch_stone = make_pbr_mat("PorchStone", (0.34, 0.39, 0.46, 1.0), roughness=0.5)
    mat_wall_ext = make_pbr_mat("WallCream", (0.88, 0.91, 0.95, 1.0), roughness=0.62)
    mat_wall_dark = make_pbr_mat("WallCharcoalTrim", (0.12, 0.16, 0.23, 1.0), roughness=0.38, metallic=0.25)
    mat_wood_slat = make_pbr_mat("WarmTeakWood", (0.52, 0.30, 0.14, 1.0), roughness=0.45)
    mat_glass = make_pbr_mat("ArchitecturalGlass", (0.55, 0.82, 0.98, 0.32), roughness=0.08, metallic=0.1, alpha=0.32)

    mat_rug = make_pbr_mat("NordicRug", (0.14, 0.24, 0.38, 1.0), roughness=0.88)
    mat_sofa = make_pbr_mat("DesignerSofaBlue", (0.18, 0.42, 0.78, 1.0), roughness=0.52)
    mat_pillow_accent = make_pbr_mat("PillowAmber", (0.95, 0.65, 0.18, 1.0), roughness=0.58)
    mat_pillow_white = make_pbr_mat("PillowCream", (0.94, 0.96, 0.98, 1.0), roughness=0.55)
    mat_marble = make_pbr_mat("CarraraMarble", (0.93, 0.95, 0.97, 1.0), roughness=0.18, metallic=0.05)
    mat_gold_brass = make_pbr_mat("BrushedBrass", (0.85, 0.68, 0.28, 1.0), roughness=0.25, metallic=0.88)
    mat_tv_screen = make_pbr_mat(
        "SmartTvScreen",
        (0.03, 0.06, 0.12, 1.0),
        roughness=0.12,
        metallic=0.4,
        emission_rgb=(0.08, 0.28, 0.55),
        emission_strength=0.45,
    )
    mat_bed_linen = make_pbr_mat("BedLinenWhite", (0.96, 0.97, 0.99, 1.0), roughness=0.58)
    mat_duvet_indigo = make_pbr_mat("DuvetIndigo", (0.32, 0.36, 0.82, 1.0), roughness=0.62)
    mat_planter_brick = make_pbr_mat("PlanterTerracotta", (0.48, 0.24, 0.12, 1.0), roughness=0.72)
    mat_leaf_dark = make_pbr_mat("FoliageDark", (0.09, 0.52, 0.22, 1.0), roughness=0.5)
    mat_leaf_bright = make_pbr_mat("FoliageBright", (0.16, 0.72, 0.32, 1.0), roughness=0.45)
    mat_led_strip = make_pbr_mat(
        "WarmLedStrip",
        (1.0, 0.88, 0.62, 1.0),
        roughness=0.2,
        emission_rgb=(1.0, 0.82, 0.45),
        emission_strength=1.8,
    )

    # 1. NỀN MÓNG BIỆT THỰ & SÀN GỖ 2 PHÒNG
    add_beveled_box("VillaBase", 0.0, -0.05, 0.7, 11.6, 0.18, 9.2, mat_foundation, 0.04, 3)
    add_beveled_box("VillaBaseTrim", 0.0, 0.03, 0.7, 11.3, 0.04, 8.9, mat_deck_trim, 0.01, 2)
    add_beveled_box("LivingRoomFloor", -2.6, 0.05, 0.0, 5.75, 0.04, 7.15, mat_oak_floor, 0.01, 2)
    add_beveled_box("BedroomFloor", 2.9, 0.05, 0.0, 5.15, 0.04, 7.15, mat_walnut_floor, 0.01, 2)

    # Bậc tam cấp trước cửa chính + Đèn LED hắt bậc thềm
    add_beveled_box("PorchStep1", -1.85, 0.02, 4.25, 2.8, 0.10, 1.35, mat_porch_stone, 0.02, 2)
    add_beveled_box("PorchStep2", -1.85, -0.02, 4.85, 2.4, 0.08, 0.65, mat_porch_stone, 0.02, 2)
    add_beveled_box("PorchLedStrip", -1.85, 0.06, 4.92, 2.3, 0.02, 0.03, mat_led_strip, 0.005, 1)

    # Lối đi đá bước dạo (Stepping stones) ra vườn cây
    for idx, sx in enumerate([-0.1, 0.75, 1.6]):
        add_beveled_box(f"GardenStepStone_{idx}", sx, 0.045, 4.35, 0.58, 0.03, 0.46, mat_porch_stone, 0.015, 2)

    # 2. HỆ TƯỜNG KIẾN TRÚC, KHUNG CỬA SỔ KÍNH & PHÀO CHỈ
    # Tường hậu (có ô cửa sổ kính phòng ngủ)
    add_beveled_box("BackWallLeft", -2.5, 1.72, -3.6, 6.2, 3.4, 0.22, mat_wall_ext, 0.02, 2)
    add_beveled_box("BackWallRightBottom", 3.1, 0.65, -3.6, 5.0, 1.25, 0.22, mat_wall_ext, 0.02, 2)
    add_beveled_box("BackWallRightTop", 3.1, 2.95, -3.6, 5.0, 0.95, 0.22, mat_wall_ext, 0.02, 2)
    add_beveled_box("BackWallRightPillarL", 1.1, 1.9, -3.6, 1.0, 1.3, 0.22, mat_wall_ext, 0.02, 2)
    add_beveled_box("BackWallRightPillarR", 4.9, 1.9, -3.6, 1.4, 1.3, 0.22, mat_wall_ext, 0.02, 2)
    # Kính cửa sổ lớn phòng ngủ
    add_beveled_box("BedroomWindowGlass", 2.9, 1.9, -3.6, 2.6, 1.25, 0.05, mat_glass, 0.005, 1)
    add_beveled_box("BedroomWindowFrameTop", 2.9, 2.5, -3.6, 2.68, 0.06, 0.25, mat_wall_dark, 0.01, 1)
    add_beveled_box("BedroomWindowFrameBot", 2.9, 1.28, -3.6, 2.68, 0.06, 0.25, mat_wall_dark, 0.01, 1)

    # Tường trái (Phòng khách) + Lam gỗ trang trí nội thất
    add_beveled_box("LeftWall", -5.5, 1.72, 0.0, 0.22, 3.4, 7.4, mat_wall_ext, 0.02, 2)
    for i in range(7):
        z_pos = -2.6 + i * 0.35
        add_beveled_box(f"LeftWallWoodSlat_{i}", -5.36, 1.72, z_pos, 0.05, 3.1, 0.12, mat_wood_slat, 0.01, 1)

    # Tường phải (Phòng ngủ) — Cắt thấp phía trước để nhìn rõ nội thất 3D
    add_beveled_box("RightWallBack", 5.5, 1.72, -1.6, 0.22, 3.4, 4.2, mat_wall_ext, 0.02, 2)
    add_beveled_box("RightWallFrontLow", 5.5, 0.58, 2.1, 0.22, 1.1, 3.2, mat_wall_ext, 0.02, 2)
    add_beveled_box("RightWallFrontCap", 5.5, 1.15, 2.1, 0.26, 0.06, 3.24, mat_wall_dark, 0.01, 2)

    # Vách ngăn giữa Phòng Khách & Phòng Ngủ (có lối thông phòng)
    add_beveled_box("MidWallBack", 0.3, 1.72, -2.0, 0.20, 3.4, 3.2, mat_wall_ext, 0.02, 2)
    add_beveled_box("MidWallFront", 0.3, 0.68, 2.45, 0.20, 1.3, 2.3, mat_wall_ext, 0.02, 2)
    add_beveled_box("MidWallCap", 0.3, 1.35, 2.45, 0.24, 0.06, 2.34, mat_wall_dark, 0.01, 2)

    # Tường mặt tiền quanh Cửa Chính + Khung cửa gỗ & Lam mặt tiền
    add_beveled_box("FrontLeftWall", -4.2, 1.4, 3.6, 2.6, 2.75, 0.24, mat_wall_ext, 0.02, 2)
    add_beveled_box("FrontRightPillar", -0.3, 1.4, 3.6, 1.4, 2.75, 0.24, mat_wall_ext, 0.02, 2)
    add_beveled_box("FrontHeader", -2.2, 2.98, 3.6, 4.9, 0.48, 0.28, mat_wall_dark, 0.02, 2)
    # Ô kính mặt tiền bên trái cửa chính
    add_beveled_box("FrontWindowGlass", -4.2, 1.55, 3.6, 1.4, 1.35, 0.28, mat_glass, 0.005, 1)

    # Dầm trần hiện đại (Ceiling Beams)
    add_beveled_box("CeilingBeamLiving1", -2.6, 3.36, -0.2, 5.8, 0.12, 0.22, mat_wall_dark, 0.015, 2)
    add_beveled_box("CeilingBeamLiving2", -2.6, 3.36, -1.8, 5.8, 0.12, 0.22, mat_wall_dark, 0.015, 2)
    add_beveled_box("CeilingBeamBed", 2.9, 3.36, -0.3, 5.2, 0.12, 0.22, mat_wall_dark, 0.015, 2)

    # 3. NỘI THẤT PHÒNG KHÁCH CAO CẤP (SOFA BO TRÒN, GỐI TỰA, BÀN TRÀ MARBLE, KỆ TV 65")
    add_beveled_box("LivingRug", -2.6, 0.075, -0.85, 3.35, 0.025, 2.45, mat_rug, 0.01, 2)

    # Sofa hiện đại vát cạnh mềm
    add_beveled_box("SofaBase", -2.6, 0.20, -2.2, 2.72, 0.16, 0.98, mat_wood_slat, 0.02, 2)
    add_beveled_box("SofaCushionL", -3.22, 0.36, -2.18, 1.18, 0.22, 0.88, mat_sofa, 0.05, 3)
    add_beveled_box("SofaCushionR", -1.98, 0.36, -2.18, 1.18, 0.22, 0.88, mat_sofa, 0.05, 3)
    add_beveled_box("SofaBackrest", -2.6, 0.68, -2.56, 2.68, 0.56, 0.24, mat_sofa, 0.05, 3)
    add_beveled_box("SofaArmLeft", -3.9, 0.48, -2.18, 0.24, 0.46, 0.96, mat_sofa, 0.04, 3)
    add_beveled_box("SofaArmRight", -1.3, 0.48, -2.18, 0.24, 0.46, 0.96, mat_sofa, 0.04, 3)
    # Gối tựa trang trí trên Sofa
    add_beveled_box("SofaPillow1", -3.55, 0.58, -2.35, 0.38, 0.34, 0.16, mat_pillow_accent, 0.04, 3)
    add_beveled_box("SofaPillow2", -2.60, 0.58, -2.36, 0.42, 0.34, 0.16, mat_pillow_white, 0.04, 3)
    add_beveled_box("SofaPillow3", -1.65, 0.58, -2.35, 0.38, 0.34, 0.16, mat_pillow_accent, 0.04, 3)

    # Bàn trà mặt đá Marble + Khung chân vàng đồng
    add_beveled_box("CoffeeTableMarbleTop", -2.6, 0.46, -0.75, 1.56, 0.06, 0.84, mat_marble, 0.02, 3)
    add_beveled_box("CoffeeTableBrassFrame", -2.6, 0.25, -0.75, 1.32, 0.36, 0.62, mat_gold_brass, 0.015, 2)

    # Kệ Tivi & Màn hình Smart TV 65 inch gắn tường trái Phòng khách
    add_beveled_box("TvConsoleCabinet", -5.05, 0.32, -0.8, 0.52, 0.46, 2.35, mat_wood_slat, 0.025, 2)
    add_beveled_box("TvConsoleTop", -5.05, 0.56, -0.8, 0.54, 0.04, 2.4, mat_marble, 0.01, 2)
    add_beveled_box("SmartTvPanel", -5.32, 1.48, -0.8, 0.06, 1.05, 1.85, mat_tv_screen, 0.01, 2)
    add_beveled_box("Soundbar", -5.02, 0.62, -0.8, 0.12, 0.08, 1.1, mat_wall_dark, 0.015, 2)

    # 4. NỘI THẤT PHÒNG NGỦ CAO CẤP (GIƯỜNG KING-SIZE, ĐẦU GIƯỜNG BỌC NỆM, TỦ QUẦN ÁO)
    add_beveled_box("BedWoodPlatform", 3.0, 0.21, -1.7, 2.56, 0.28, 2.95, mat_wood_slat, 0.03, 3)
    add_beveled_box("BedHeadboardWood", 3.0, 0.78, -3.12, 2.64, 1.38, 0.16, mat_wood_slat, 0.025, 2)
    add_beveled_box("BedHeadboardCushion", 3.0, 0.78, -3.02, 2.36, 1.02, 0.08, mat_pillow_white, 0.03, 2)
    add_beveled_box("BedMattress", 3.0, 0.45, -1.65, 2.34, 0.28, 2.68, mat_bed_linen, 0.05, 3)
    add_beveled_box("BedDuvet", 3.0, 0.47, -1.20, 2.38, 0.30, 1.78, mat_duvet_indigo, 0.05, 3)
    add_beveled_box("BedPillowL", 2.42, 0.65, -2.62, 0.86, 0.16, 0.48, mat_bed_linen, 0.04, 3)
    add_beveled_box("BedPillowR", 3.58, 0.65, -2.62, 0.86, 0.16, 0.48, mat_bed_linen, 0.04, 3)

    # Tủ đầu giường (Nightstand) & Tủ quần áo (Wardrobe)
    add_beveled_box("NightstandBody", 1.25, 0.34, -2.8, 0.66, 0.56, 0.58, mat_wood_slat, 0.02, 2)
    add_beveled_box("NightstandTop", 1.25, 0.63, -2.8, 0.68, 0.04, 0.60, mat_marble, 0.01, 2)
    add_beveled_box("BedroomWardrobe", 4.92, 1.35, -0.35, 0.72, 2.55, 1.85, mat_wood_slat, 0.025, 2)
    add_beveled_box("WardrobeHandle", 4.54, 1.35, -0.35, 0.03, 0.85, 0.04, mat_gold_brass, 0.005, 1)

    # 5. BỒN CÂY SÂN VƯỜN & TIỂU CẢNH TRƯỚC NHÀ (KHỚP VỊ TRÍ MÁY BƠM D3 & YL-69 A0)
    # Tọa độ bồn cây trong Three.js: (2.25, 0.27, 4.35)
    add_beveled_box("GardenPlanterBox", 2.25, 0.26, 4.35, 2.84, 0.46, 1.28, mat_planter_brick, 0.03, 2)
    add_beveled_box("GardenPlanterRim", 2.25, 0.49, 4.35, 2.92, 0.05, 1.34, mat_porch_stone, 0.015, 2)

    # 3 Cụm cây xanh đa tầng trong bồn cây sân vườn
    for idx, px in enumerate([1.50, 2.20, 2.90]):
        add_cylinder_3d(f"TreeTrunk_{idx}", px, 0.62, 4.35, 0.05, 0.42, mat_wood_slat, 16)
        add_uv_sphere(
            f"TreeCrownMain_{idx}",
            px,
            0.88,
            4.35,
            0.30 + (0.05 if idx == 1 else 0.0),
            mat_leaf_dark if idx % 2 == 0 else mat_leaf_bright,
            (1.1, 0.92, 1.1),
        )
        add_uv_sphere(
            f"TreeCrownTop_{idx}",
            px + 0.10,
            1.08,
            4.42,
            0.21,
            mat_leaf_bright,
            (1.0, 0.9, 1.0),
        )

    # Chậu cây cảnh đặt cạnh bậc thềm cửa chính
    add_cylinder_3d("PorchPot", -3.35, 0.28, 4.15, 0.24, 0.42, mat_planter_brick, 20)
    add_uv_sphere("PorchPlantFoliage", -3.35, 0.64, 4.15, 0.30, mat_leaf_bright, (1.0, 1.15, 1.0))

    # Xuất ra file glTF Binary (.glb)
    out_dir = pathlib.Path(__file__).resolve().parent.parent / "simulator" / "static" / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "smarthome_villa.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(out_file),
        export_format="GLB",
        export_yup=True,
        export_apply=True,
        export_materials="EXPORT",
    )
    print(f"[BLENDER 5.2 EXPORT SUCCESS] Saved {out_file} ({out_file.stat().st_size} bytes)")


if __name__ == "__main__":
    build_villa()
