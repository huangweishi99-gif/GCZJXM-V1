# -*- coding: utf-8 -*-
"""定稿口径特殊清单：优先于主材表/弱整项误套。"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from src.normalize.text import normalize_name, normalize_unit


def lookup_ceiling_opening_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """天棚/吊顶面灯具开孔：纯人工（深海定稿 6 元/个）。"""
    if normalize_name(name) != normalize_name("天棚面开孔"):
        return None, ""
    if normalize_unit(unit) not in ("个",):
        return None, ""
    text = normalize_name(f"{name}\n{feature}")
    if not re.search(r"开孔|灯具", text):
        return None, ""
    return {
        "material_main": 0.0,
        "material_loss_rate": 0.0,
        "material_aux": 0.0,
        "labor": 6.0,
        "machinery": 0.0,
    }, "[定稿口径]天棚面灯具开孔 人工6元/个"


def lookup_stone_arc_guard_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """ST 石材护角弧形：干挂弧形收边，非普通 ST 表价铺贴。"""
    nn = normalize_name(name)
    if not re.search(r"护角弧形|石材护角", nn):
        return None, ""
    if normalize_unit(unit) not in ("m2", "㎡"):
        return None, ""
    if not re.search(r"ST-\d+", nn, re.I):
        return None, ""
    return {
        "material_main": 1425.0,
        "material_loss_rate": 0.0,
        "material_aux": 188.2,
        "labor": 200.0,
        "machinery": 0.0,
    }, "[定稿口径]ST石材护角弧形 干挂收边"


def lookup_washbasin_counter_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """洗漱台：ST-03 台面 + 角钢骨架 + 阻燃板防水（水平投影综合）。"""
    if normalize_name(name) != normalize_name("洗漱台"):
        return None, ""
    if normalize_unit(unit) not in ("m2", "㎡"):
        return None, ""
    text = normalize_name(f"{name}\n{feature}")
    if not re.search(r"ST-03|角钢|骨架", text):
        return None, ""
    return {
        "material_main": 787.5,
        "material_loss_rate": 0.0,
        "material_aux": 141.82,
        "labor": 150.0,
        "machinery": 0.01,
    }, "[定稿口径]洗漱台 ST-03+钢架阻燃板 投影综合"


def lookup_epoxy_floor_skirting_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """地坪漆踢脚线（海德地库 CH-03a 等）。"""
    nn = normalize_name(name)
    text = normalize_name(f"{name}\n{feature}")
    if not re.search(r"地坪漆踢脚|CH-03", nn + text):
        return None, ""
    if normalize_unit(unit) not in ("m", "米"):
        return None, ""
    hm = re.search(r"[Hh](\d+)", nn + text)
    height = int(hm.group(1)) if hm else 100
    if height <= 50:
        return {
            "material_main": 2.5,
            "material_loss_rate": 0.0,
            "material_aux": 1.325,
            "labor": 10.0,
            "machinery": 0.0,
        }, "[定稿口径]地坪漆踢脚线 H50"
    return {
        "material_main": 4.5,
        "material_loss_rate": 0.0,
        "material_aux": 1.35,
        "labor": 12.0,
        "machinery": 0.0,
    }, "[定稿口径]地坪漆踢脚线 H100"


def lookup_haide_basement_pt_paint_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """海德地库/坡道 PT 涂料（金标准：主材5.5 人工22.5；原顶投影28.055）。"""
    if normalize_unit(unit) not in ("m2", "㎡"):
        return None, ""
    if not re.search(r"PT-0[125]", name, re.I):
        return None, ""
    if not re.search(r"地库装饰|坡道装饰", feature or ""):
        return None, ""
    text = normalize_name(f"{name}\n{feature}")
    if re.search(r"投影面", text):
        return {
            "material_main": 5.555,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 22.5,
            "machinery": 0.0,
        }, "[定稿口径]海德地库 PT 原顶投影面"
    return {
        "material_main": 5.5,
        "material_loss_rate": 0.0,
        "material_aux": 6.235,
        "labor": 22.5,
        "machinery": 0.0,
    }, "[定稿口径]海德地库 PT 一底两面"


def lookup_parking_line_marking_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """停车位移线、划线：材料+人工综合（开市客/深海校正口径）。"""
    nn = normalize_name(name)
    text = normalize_name(f"{name}\n{feature}")
    if not re.search(
        r"停车位移线|车位.*划线|交通划线|工位划线|热融漆划线|停车场划线|划线.*喷字",
        text,
    ):
        return None, ""
    unit_n = normalize_unit(unit)
    if unit_n not in ("个", "车位", "项", "m", "米", "m2", "㎡"):
        return None, ""
    if unit_n in ("m", "米"):
        return {
            "material_main": 4.5,
            "material_loss_rate": 0.0,
            "material_aux": 1.0,
            "labor": 8.0,
            "machinery": 0.0,
        }, "[定稿口径]地面热融漆划线 按米"
    if unit_n in ("m2", "㎡"):
        return {
            "material_main": 3.5,
            "material_loss_rate": 0.0,
            "material_aux": 0.5,
            "labor": 5.5,
            "machinery": 0.0,
        }, "[定稿口径]划线措施 按面积"
    return {
        "material_main": 90.0,
        "material_loss_rate": 0.0,
        "material_aux": 8.0,
        "labor": 38.0,
        "machinery": 0.0,
    }, "[定稿口径]停车场划线/喷字 按车位"


def lookup_ceiling_slot_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """天棚面开槽嵌线性灯：延长米（实际样本人工26.4,机械3.6）。"""
    nn = normalize_name(name)
    if "天棚面开槽" not in nn and not re.search(r"天棚.*开槽|开槽.*100", nn):
        return None, ""
    if normalize_unit(unit) not in ("m", "米"):
        return None, ""
    return {
        "material_main": 0.0,
        "material_loss_rate": 0.0,
        "material_aux": 0.0,
        "labor": 26.4,
        "machinery": 3.6,
    }, "[实际样本]天棚面开槽嵌线性灯 人工26.4+机械3.6元/m"


def lookup_curtain_box_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """窗帘盒（200mm*200mm等规格）。"""
    nn = normalize_name(name)
    text = normalize_name(f"{name}\n{feature}")
    if "窗帘盒" not in nn:
        return None, ""
    unit_n = normalize_unit(unit)
    if unit_n not in ("m", "米"):
        return None, ""
    # 实际样本校准：
    # 1. 窗帘盒（200mm*200mm）：人工55元/m（record_id=18971等）
    # 2. 窗帘盒（钢结构龙骨+阻燃板基层+9.5mm石膏板）：主材131.67, 人工55, 辅材8.5（2026审计校准，12条同值）
    # 3. 石膏板顶窗帘盒：人工51.53元/m（record_id=3545等）
    # 4. 复杂窗帘盒（钢结构/钢板基层）：原主材39.02/人工117.05 已按多数实值校准为 131.67/55/8.5
    
    # 中山「窗帘盒(200+200mm)」：名称用加号，与珠海「200mm*200mm」双层板不是同一做法
    # （全库 9 条同值 主材22/人工15/辅材2.5，含 230+200、300+200）。
    # 必须先于下方 *200 双层板分支，否则 200+200 会被归一化后误套 0/55/29.67。
    if re.search(r"\d+\s*\+\s*\d+", nn):
        return {
            "material_main": 22.0,
            "material_loss_rate": 0.0,
            "material_aux": 2.5,
            "labor": 15.0,
            "machinery": 0.0,
        }, "[实际样本]窗帘盒(加号规格·方形石膏板) 主材22/人工15元/m"

    # 先检查标准规格（100*200 / 200*200 双层板+轻钢龙骨，简单定价）
    # 实际样本：100*200 与 200*200 同价 main=0,aux=29.67,labor=55,mach=29.67（record_id=9782等）
    if re.search(r"(?:100|200)\s*[*×xX]\s*200|200mm.*200mm|100mm.*200mm", nn):
        return {
            "material_main": 0.0,
            "material_loss_rate": 0.0,
            "material_aux": 29.67,
            "labor": 55.0,
            "machinery": 29.67,
        }, "[实际样本]窗帘盒100*200/200*200 人工55元/m"

    # 再检查是否含钢结构/钢板基层（复杂窗帘盒，如钢结构龙骨+阻燃板基层+9.5mm石膏板）
    # 注意：轻钢龙骨是所有标准窗帘盒的常规基层，不能触发复杂分支；
    # 2026审计校准：钢结构龙骨+阻燃板基层实 主材131.67/人工55/辅材8.5（12条同值，原117.05为少数批次）
    if re.search(r"钢结构|钢板基层", text):
        return {
            "material_main": 131.67,
            "material_loss_rate": 0.0,
            "material_aux": 8.5,
            "labor": 55.0,
            "machinery": 0.0,
        }, "[实际样本]复杂窗帘盒(钢结构+阻燃板基层) 主材131.67/人工55元/m"
    
    # 匹配石膏板顶窗帘盒
    if re.search(r"石膏板顶.*窗帘盒|石膏板顶", text):
        return {
            "material_main": 46.22,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 51.53,
            "machinery": 0.75,
        }, "[实际样本]石膏板顶窗帘盒 人工51.53元/m"
    
    # 默认定价：使用中位值55元/m
    return {
        "material_main": 0.0,
        "material_loss_rate": 0.0,
        "material_aux": 0.0,
        "labor": 55.0,
        "machinery": 0.0,
    }, "[默认]窗帘盒 人工55元/m"


def lookup_light_slot_linear_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """灯槽延长米（100×200 等）。"""
    nn = normalize_name(name)
    text = normalize_name(f"{name}\n{feature}")
    if "灯槽" not in nn or re.search(r"开槽|涂料|无机", nn):
        return None, ""
    if normalize_unit(unit) not in ("m", "米"):
        return None, ""
    # 实际样本校准：
    # 100×200灯槽：主材0, 辅材22.09, 人工50, 机械22.09
    # 135×100灯槽：主材0, 辅材22.09, 人工50, 机械22.09
    # 统一所有灯槽规格为人工50元/m
    
    # 匹配100×200规格
    if re.search(r"100\s*mm?\s*[*×xX]\s*200\s*mm?|100\s*[*×xX]\s*200", nn):
        return {
            "material_main": 0.0,
            "material_loss_rate": 0.0,
            "material_aux": 22.09,
            "labor": 50.0,
            "machinery": 22.09,
        }, "[实际样本]100×200灯槽 人工50元/m"
    
    # 匹配135×100规格（或其他非100×200规格）
    if re.search(r"135\s*[*×xX]\s*100|135mm.*100mm|135.*100", nn):
        return {
            "material_main": 0.0,
            "material_loss_rate": 0.0,
            "material_aux": 22.09,
            "labor": 50.0,
            "machinery": 22.09,
        }, "[实际样本]135×100灯槽 人工50元/m"
    
    # 其他规格灯槽统一按人工50元/m
    return {
        "material_main": 0.0,
        "material_loss_rate": 0.0,
        "material_aux": 22.09,
        "labor": 50.0,
        "machinery": 22.09,
    }, "[实际样本]灯槽 统一人工50元/m"


def lookup_plant_pot_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """室内绿植盆栽（名称即植物名）。"""
    if normalize_unit(unit) not in ("盆", "棵", "株", "个", "套"):
        return None, ""
    nn = normalize_name(name)
    if not re.search(
        r"虎皮兰|天门冬|万年青|绿萝|发财树|散尾葵|琴叶榕|天堂鸟|龟背竹|袖珍椰子|植物|盆栽",
        nn,
    ):
        return None, ""
    if re.search(r"种植土|绿化工程|乔木|灌木", nn):
        return None, ""
    # 狐尾天门冬、万年青等高档绿植价格较高
    if re.search(r"天门冬|万年青", nn):
        return {
            "material_main": 75.0,
            "material_loss_rate": 0.0,
            "material_aux": 5.0,
            "labor": 20.0,
            "machinery": 0.0,
        }, "[市场参考]高档绿植盆栽"
    return {
        "material_main": 32.0,
        "material_loss_rate": 0.0,
        "material_aux": 3.0,
        "labor": 8.0,
        "machinery": 0.0,
    }, "[市场参考]室内盆栽"


def lookup_insulation_panel_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """聚氨酯发泡保温装饰板。"""
    nn = normalize_name(name)
    if not re.search(r"聚氨酯.*保温|保温装饰板|发泡保温", nn):
        return None, ""
    if normalize_unit(unit) not in ("m2", "㎡"):
        return None, ""
    # 实际样本校准：record_id=245，主材85.0，人工18.53
    return {
        "material_main": 85.0,
        "material_loss_rate": 0.03,
        "material_aux": 0.0,
        "labor": 18.53,
        "machinery": 0.37,
    }, "[实际样本]聚氨酯保温装饰板"


def lookup_color_steel_partition_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """彩钢板隔墙/天花。"""
    nn = normalize_name(name)
    if not re.search(r"彩钢板", nn):
        return None, ""
    if normalize_unit(unit) not in ("m2", "㎡"):
        return None, ""
    # 不含龙骨价格较低，含龙骨/超高价格较高
    if "不含龙骨" in nn:
        main, labor = 55.0, 18.0
    elif "超高" in nn:
        main, labor = 120.0, 85.0
    else:
        main, labor = 100.0, 40.0
    return {
        "material_main": main,
        "material_loss_rate": 0.03,
        "material_aux": 12.0 if main >= 100 else 8.0,
        "labor": labor,
        "machinery": 2.0,
    }, "[市场参考]彩钢板隔墙/天花"


def lookup_roll_door_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """快速卷帘门（电动）。"""
    nn = normalize_name(name)
    if not re.search(r"卷帘门|卷闸门", nn):
        return None, ""
    if normalize_unit(unit) not in ("樘", "套", "扇", "项", "个"):
        return None, ""
    sm = re.search(r"(\d+(?:\.\d+)?)\s*[mM米]\s*[*×xX]\s*(\d+(?:\.\d+)?)", nn)
    area = float(sm.group(1)) * float(sm.group(2)) if sm else 9.0
    # 电动快速卷帘门价格较高，含电机和控制系统
    main = round(2200.0 * area, 2)
    return {
        "material_main": main,
        "material_loss_rate": 0.0,
        "material_aux": round(main * 0.04, 2),
        "labor": round(500 + area * 110, 2),
        "machinery": 50.0,
    }, f"[市场参考]电动卷帘门约{area:g}㎡"


def lookup_stainless_wrap_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """楼梯/柱包封不锈钢、电梯门头、不锈钢包边。"""
    nn = normalize_name(name)
    text = normalize_name(f"{name}\n{feature}")
    # LED灯带/线性灯（如"电梯门头天花内嵌LED灯带-SL03"）交由 mep_install 灯带分支处理，避免误吞为不锈钢包封
    if re.search(r"LED灯带|灯带|线性灯", text):
        return None, ""
    if not re.search(r"包封不锈钢|不锈钢门头|电梯.*门头|门套不锈钢|不锈钢.*包边|包边.*不锈钢", text):
        return None, ""
    unit_n = normalize_unit(unit)
    if unit_n in ("m2", "㎡"):
        # 实际样本校准：record_id=233，楼梯两侧包封不锈钢，主材350，人工63.48
        return {
            "material_main": 350.0,
            "material_loss_rate": 0.05,
            "material_aux": 0.0,
            "labor": 63.48,
            "machinery": 2.1,
        }, "[实际样本]不锈钢包封 按面积"
    if unit_n in ("m", "米"):
        # MT-05喷砂黑钛不锈钢包边：record_id=20930，主材101.0，人工35.0
        if re.search(r"MT-05|喷砂.*黑钛", text):
            return {
                "material_main": 101.0,
                "material_loss_rate": 0.03,
                "material_aux": 2.75,
                "labor": 35.0,
                "machinery": 0.0,
            }, "[实际样本]MT-05喷砂黑钛不锈钢包边"
        return {
            "material_main": 85.0,
            "material_loss_rate": 0.03,
            "material_aux": 12.0,
            "labor": 45.0,
            "machinery": 1.0,
        }, "[市场参考]不锈钢包封/门套 按延长米"
    return None, ""


def lookup_copper_bar_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """实心铜条收边。"""
    nn = normalize_name(name)
    if not re.search(r"实心铜条|铜条", nn):
        return None, ""
    if normalize_unit(unit) not in ("m", "米"):
        return None, ""
    wm = re.search(r"(\d+(?:\.\d+)?)\s*mm", nn)
    width = float(wm.group(1)) if wm else 5.0
    main = round(18.0 + width * 4.5, 2)
    return {
        "material_main": main,
        "material_loss_rate": 0.02,
        "material_aux": 3.0,
        "labor": round(12.0 + width * 0.8, 2),
        "machinery": 0.0,
    }, f"[市场参考]铜条{width:g}mm"


def lookup_sanitary_accessory_extra_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """毛巾杆等卫浴配件。"""
    nn = normalize_name(name)
    if not re.search(r"毛巾杆|纸巾盒|皂液器|浴帘杆", nn):
        return None, ""
    if normalize_unit(unit) not in ("个", "套", "只", "根"):
        return None, ""
    return {
        "material_main": 65.0,
        "material_loss_rate": 0.0,
        "material_aux": 5.0,
        "labor": 25.0,
        "machinery": 0.0,
    }, "[市场参考]卫浴配件"


def lookup_public_tile_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """地铁/车站等公装块料：湿贴含砂浆垫层，不套户型精装 55/48。

    800×800 防滑砖约 55 元/㎡；盲道砖约 80。垫层按厚度进辅材，
    上翻、防水另列，不重复计入。
    """
    nn = normalize_name(name)
    text = normalize_name(f"{name}\n{feature}")
    unit_n = normalize_unit(unit)
    if unit_n not in ("m2", "㎡", "m", "米"):
        return None, ""
    if not re.search(r"站厅|站台|地铁|候车|出入口|设备区|公共区", text):
        return None, ""
    if not re.search(r"地砖|块料|盲道", nn):
        return None, ""

    bed = 20.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*mm", text)
    if m:
        thick = float(m.group(1))
        if 10 <= thick <= 150:
            bed = round(thick * 0.85, 1)
    is_tactile = bool(re.search(r"盲道", nn))
    if unit_n in ("m", "米"):
        # 100mm 高瓷砖踢脚：砖约 12 元/m，水泥砂浆粘贴
        return {
            "material_main": 18.0 if is_tactile else 12.0,
            "material_loss_rate": 0.03,
            "material_aux": 3.5,
            "labor": 16.0 if is_tactile else 18.0,
            "machinery": 0.0,
        }, "[市场参考]公装瓷砖踢脚"
    return {
        "material_main": 80.0 if is_tactile else 55.0,
        "material_loss_rate": 0.03,
        "material_aux": bed,
        "labor": 68.0 if is_tactile else 65.0,
        "machinery": 2.5,
    }, "[市场参考]公装地砖湿贴(含砂浆垫层)"


def lookup_tile_skirting_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """块料/瓷砖踢脚：常见为局部人工补项，先作参考价。"""
    nn = normalize_name(name)
    if not re.search(r"块料踢脚|瓷砖踢脚|地砖踢脚", nn):
        return None, ""
    unit_n = normalize_unit(unit)
    if unit_n in ("m2", "㎡") and re.search(r"50mm.*CT-06.*瓷砖踢脚|CT-06.*瓷砖踢脚", nn, re.I):
        return {
            "material_main": 105.0,
            "material_loss_rate": 0.0,
            "material_aux": 16.5,
            "labor": 120.0,
            "machinery": 0.5,
        }, "[复核参考]50mm CT-06瓷砖踢脚"
    if unit_n in ("m2", "㎡"):
        return {
            "material_main": 0.0,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 80.0,
            "machinery": 0.0,
        }, "[市场参考]块料踢脚人工补项 按面积"
    if unit_n in ("m", "米"):
        text = normalize_name(f"{name}\n{feature}")
        # 特征写明瓷砖规格时砖是主材，不能只给人工
        if re.search(r"瓷砖|地砖", text):
            return {
                "material_main": 12.0,
                "material_loss_rate": 0.03,
                "material_aux": 3.5,
                "labor": 18.0,
                "machinery": 0.0,
            }, "[市场参考]瓷砖踢脚(含砖)"
        return {
            "material_main": 0.0,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 18.0,
            "machinery": 0.0,
        }, "[市场参考]块料踢脚人工补项 按米"
    return None, ""


def lookup_hand_painted_mural_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """手绘壁画/SP 艺术墙面：项目差异大，仅给复核参考。"""
    text = normalize_name(f"{name}\n{feature}")
    if not re.search(r"手绘壁画|壁画|艺术手绘|SP-\d+", text, re.I):
        return None, ""
    if normalize_unit(unit) not in ("m2", "㎡"):
        return None, ""
    return {
        "material_main": 1950.0,
        "material_loss_rate": 0.0,
        "material_aux": 50.0,
        "labor": 350.0,
        "machinery": 10.5,
    }, "[市场参考]手绘壁画/SP艺术墙面"


def lookup_review_priority_small_item_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """明确小项优先于弱整项，但仅作为复核参考。"""
    nn = normalize_name(name)
    text = normalize_name(f"{name}\n{feature}")
    unit_n = normalize_unit(unit)
    if unit_n in ("张", "块") and re.fullmatch(r"石膏板", nn):
        return {
            "material_main": 31.0,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 0.0,
            "machinery": 0.0,
        }, "[市场参考]纯材料-石膏板"
    if unit_n in ("m2", "㎡") and re.fullmatch(r"CFC保温", nn, re.I):
        return {
            "material_main": 0.0,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 28.0,
            "machinery": 0.0,
        }, "[市场参考]CFC保温人工补项"
    exact_table = (
        (
            r"外围木板基层.*不含龙骨",
            ("m2", "㎡"),
            (58.12, 0.0, 13.31, 0.0),
            "外围木板基层不含龙骨",
        ),
        (
            r"内嵌卡座.*儿童区",
            ("m2", "㎡"),
            (932.65, 20.0, 72.99, 10.26),
            "内嵌卡座儿童区",
        ),
        (
            r"设备三相四孔插座",
            ("个", "套"),
            (177.95, 0.0, 12.49, 0.86),
            "设备三相四孔插座",
        ),
        (
            r"双扇玻璃门",
            ("樘", "套"),
            (4200.0, 0.0, 944.3, 15.87),
            "双扇玻璃门",
        ),
        (
            r"成品隔油池.*玻璃钢",
            ("m3", "m³", "立方米"),
            (300.0, 150.0, 285.0, 15.0),
            "玻璃钢成品隔油池",
        ),
        (
            r"平面防水卷材",
            ("m2", "㎡"),
            (52.28, 0.0, 6.35, 0.0),
            "SBS平面防水卷材",
        ),
        (
            r"成品软膜灯箱",
            ("m2", "㎡"),
            (401.23, 0.0, 103.42, 12.76),
            "成品软膜灯箱",
        ),
        (
            r"AL-03.*黑色型材踢脚线|黑色型材踢脚线",
            ("m", "米"),
            (13.0, 0.97, 12.3, 0.65),
            "AL-03黑色型材踢脚线",
        ),
        (
            r"装饰屏风.*1810|1810.*装饰屏风",
            ("m2", "㎡"),
            (1415.0, 0.0, 55.0, 0.0),
            "装饰屏风（1810mm宽）",
        ),
        (
            r"吊顶.*标高|标高.*吊顶|多层叠型",
            ("㎡", "m2"),
            (0.0, 0.0, 150.0, 0.0),
            "造型石膏板吊顶（高标高/多层叠型）",
        ),
    )
    for pat, units, comps, label in exact_table:
        if unit_n in units and re.search(pat, text, re.I):
            main, aux, labor, mach = comps
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[市场参考]明确小项-{label}"
    return None, ""


def lookup_finish_exact_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """明确名称的饰面/修补项，避免主材价库套通用份额模板。"""
    nn = normalize_name(name)
    text = normalize_name(f"{name}\n{feature}")
    unit_n = normalize_unit(unit)

    if unit_n in ("m2", "㎡") and re.search(r"电梯.*不锈钢.*门头|不锈钢.*电梯.*门头", nn):
        return {
            "material_main": 450.0,
            "material_loss_rate": 0.0,
            "material_aux": 54.0,
            "labor": 110.0,
            "machinery": 1.2,
        }, "[复核参考]电梯不锈钢门头"
    if unit_n in ("m2", "㎡") and re.search(r"过门石|门槛石", nn):
        # 名称含"门槛石"但主工作实为找平/找坡（如"平面砂浆找平层（门槛石）"）时不是门槛石项，
        # 不得套过门石湿贴市场价，放行后续找平类定价
        if re.search(r"找平|找坡", nn):
            return None, ""
        # 编号石材门槛石（如 ST-02，石材品种随编号定、盘间价差大）不套市场档，放行编号/历史层
        if re.search(r"ST-?\d{1,2}|编号[\s：:]*ST|大理石|天然石|人造石|米黄|爵士白|雅士白|黑金花", text):
            return None, ""
        return {
            "material_main": 110.0,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 50.31,
            "machinery": 1.66,
        }, "[市场参考]过门石湿贴"
    if unit_n in ("m2", "㎡") and re.search(r"局部.*瓷砖.*修补|瓷砖.*修补", nn):
        return {
            "material_main": 120.0,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 93.29,
            "machinery": 3.16,
        }, "[市场参考]局部瓷砖修补"
    if unit_n in ("m", "米") and re.search(r"石材窗台板", nn):
        return {
            "material_main": 33.71,
            "material_loss_rate": 0.0,
            "material_aux": 16.86,
            "labor": 32.02,
            "machinery": 1.69,
        }, "[市场参考]石材窗台板窄板"
    if unit_n in ("m2", "㎡") and re.search(r"红色定制面包砖|面包砖", nn):
        return {
            "material_main": 85.0,
            "material_loss_rate": 0.0,
            "material_aux": 16.0,
            "labor": 60.0,
            "machinery": 0.0,
        }, "[市场参考]定制面包砖"
    if unit_n in ("m2", "㎡") and re.search(r"防辐射.*细石混凝土.*楼地面|细石混凝土楼地面F9", text):
        return {
            "material_main": 0.0,
            "material_loss_rate": 0.0,
            "material_aux": 53.0,
            "labor": 48.0,
            "machinery": 0.0,
        }, "[市场参考]防辐射细石混凝土楼地面"
    if unit_n in ("m2", "㎡") and re.search(r"瓷砖排水明沟|排水明沟", nn):
        return {
            "material_main": 33.0,
            "material_loss_rate": 0.0,
            "material_aux": 19.36,
            "labor": 40.0,
            "machinery": 0.0,
        }, "[市场参考]瓷砖排水明沟"
    # 调差-增减一道龙骨（含岩棉）
    # 实际样本：75龙骨主材53.75, 人工30.12；100龙骨主材66.18, 人工30.12
    if unit_n in ("m2", "㎡") and re.search(r"调差.*增减.*龙骨|增减.*龙骨.*岩棉", text):
        # 匹配龙骨规格
        ks = re.search(r"(\d+)\s*龙骨", text)
        ksize = int(ks.group(1)) if ks else 75
        keel_table = {
            75: (53.75, 30.12),
            100: (66.18, 30.12),
            120: (78.82, 30.12),
            150: (66.16, 52.48),
        }
        main, labor = keel_table.get(ksize, (53.75, 30.12))
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": labor,
            "machinery": 0.0,
        }, f"[实际样本]增减一道{ksize}龙骨(含岩棉)"
    # 调差-增减一道石膏板
    # 实际样本：9.5mm石膏板主材10.91, 人工11.85
    if unit_n in ("m2", "㎡") and re.search(r"调差.*增减.*石膏板|增减.*石膏板", text):
        gs = re.search(r"(\d+(?:\.\d+)?)\s*mm.*石膏板|石膏板.*(\d+(?:\.\d+)?)\s*mm", text)
        gs_thickness = float(gs.group(1) or gs.group(2)) if gs else 9.5
        gypsum_table = {
            9.5: (10.91, 11.85),
            12.0: (12.5, 13.5),
        }
        main, labor = gypsum_table.get(gs_thickness, (10.91, 11.85))
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": labor,
            "machinery": 0.0,
        }, f"[实际样本]增减一道{gs_thickness}mm石膏板"
    # 调差-增减一道钢化玻璃/防火玻璃
    # 实际样本：6mm超白玻璃主材105；12mm钢化玻璃主材253；15mm防火钢化玻璃主材385；19mm钢化玻璃主材320
    if unit_n in ("m2", "㎡") and re.search(r"调差.*增减.*玻璃|增减.*玻璃", text):
        gl = re.search(r"(\d+)\s*mm.*玻璃|玻璃.*(\d+)\s*mm", text)
        gl_thickness = int(gl.group(1) or gl.group(2)) if gl else 12
        is_fire = "防火" in text
        is_super_white = "超白" in text
        if is_fire:
            glass_table = {
                12: (220.0, 0.0),
                15: (385.0, 0.0),
            }
        elif is_super_white:
            glass_table = {
                6: (105.0, 0.0),
                8: (135.0, 0.0),
                10: (165.0, 0.0),
            }
        else:
            glass_table = {
                6: (90.0, 0.0),
                8: (120.0, 0.0),
                10: (180.0, 0.0),
                12: (253.0, 0.0),
                15: (320.0, 0.0),
                19: (320.0, 0.0),
            }
        main, labor = glass_table.get(gl_thickness, (253.0, 0.0))
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": labor,
            "machinery": 0.0,
        }, f"[实际样本]增减一道{gl_thickness}mm{'超白' if is_super_white else ''}{'防火' if is_fire else ''}钢化玻璃"
    # CT-01浅灰色仿大理石防滑地砖
    # 实际样本：主材135.74, 人工76.5
    if unit_n in ("m2", "㎡") and re.search(r"CT-01.*仿大理石|CT-01.*防滑地砖|浅灰色.*仿大理石", text):
        return {
            "material_main": 135.74,
            "material_loss_rate": 0.0,
            "material_aux": 18.5,
            "labor": 76.5,
            "machinery": 3.0,
        }, "[实际样本]CT-01浅灰色仿大理石防滑地砖"
    # 3mm厚铝单板（氟碳喷涂）
    # 实际样本：主材522.48, 人工160
    if unit_n in ("m2", "㎡") and re.search(r"铝单板|氟碳喷涂.*铝板", text):
        al = re.search(r"(\d+(?:\.\d+)?)\s*mm", text)
        al_thickness = float(al.group(1)) if al else 3.0
        if al_thickness >= 2.5:
            main = round(350 + al_thickness * 57.5, 2)  # 3mm: ~522.48
        else:
            main = round(280 + al_thickness * 40, 2)
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": 25.0,
            "labor": 160.0,
            "machinery": 5.0,
        }, f"[实际样本]{al_thickness}mm铝单板(氟碳喷涂)"
    # 电梯门门头上部（优先匹配，即使特征含MT-02）
    # 实际样本：主材217.72, 辅材108.86, 人工206.83, 机械10.89
    if unit_n in ("m2", "㎡") and re.search(r"电梯.*门头.*上部|门头.*上部", nn):
        return {
            "material_main": 217.72,
            "material_loss_rate": 0.03,
            "material_aux": 108.86,
            "labor": 206.83,
            "machinery": 10.89,
        }, "[实际样本]电梯门门头上部"
    # MT-02喷砂香槟金系列（不同类型定价不同）
    # 实际样本：电梯内嵌收边 主材380, 人工70, 辅材87, 机械0；门套 主材354.82, 人工88.7, 辅材39.42, 机械9.86；不锈钢门 主材706.68, 人工176.67, 辅材78.52, 机械19.63
    # 中山窗套/门套（云湾MT-01/02/05）实_主材200,人工68,辅材19,机0（与 market_reference.stainless_frame_zs 一致）
    if unit_n in ("m2", "㎡") and re.search(r"MT-02|喷砂.*香槟金", text):
        if re.search(r"窗套", text):
            return {
                "material_main": 200.0,
                "material_loss_rate": 0.0,
                "material_aux": 19.0,
                "labor": 68.0,
                "machinery": 0.0,
            }, "[实际样本]MT-02喷砂香槟金窗套(中山云湾)"
        if re.search(r"电梯.*内嵌.*收边|内嵌收边", text):
            return {
                "material_main": 380.0,
                "material_loss_rate": 0.03,
                "material_aux": 87.0,
                "labor": 70.0,
                "machinery": 0.0,
            }, "[实际样本]MT-02喷砂香槟金(电梯内嵌收边)"
        elif re.search(r"门套", text):
            return {
                "material_main": 354.82,
                "material_loss_rate": 0.03,
                "material_aux": 39.42,
                "labor": 88.7,
                "machinery": 9.86,
            }, "[实际样本]MT-02喷砂香槟金门套"
        elif re.search(r"门", text):
            return {
                "material_main": 706.68,
                "material_loss_rate": 0.03,
                "material_aux": 78.52,
                "labor": 176.67,
                "machinery": 19.63,
            }, "[实际样本]MT-02喷砂香槟金不锈钢门"
        else:
            # 默认按电梯内嵌收边定价
            return {
                "material_main": 380.0,
                "material_loss_rate": 0.03,
                "material_aux": 87.0,
                "labor": 70.0,
                "machinery": 0.0,
            }, "[实际样本]MT-02喷砂香槟金(默认)"
    # 外幕墙烤漆铝板（干挂铝板，含龙骨折边防水；特征含"防水"易误入防水分支，2026审计校准）
    # 实际样本：2mm厚 实_主材542.35人工104.12；3mm厚 实_主材700-750人工104-120
    if unit_n in ("m2", "㎡") and re.search(r"烤漆铝板|干挂铝板", text):
        al = re.search(r"(\d+(?:\.\d+)?)\s*mm", text)
        al_thickness = float(al.group(1)) if al else 3.0
        if al_thickness >= 2.5:
            main, labor = 725.0, 112.0
        else:
            main, labor = 542.35, 104.12
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": labor,
            "machinery": 26.0,
        }, f"[实际样本]外幕墙烤漆铝板 {al_thickness}mm"
    # 防水层（不同类型定价不同）
    # 实际样本：立面聚氨酯防水 主材35, 人工19.85；1.2mm JS防水 主材22.5, 人工18；2mm JS防水 主材30, 人工42
    # 优先用项目名(nn)判断厚度，避免特征中的干扰信息
    if unit_n in ("m2", "㎡") and re.search(r"防水", text):
        # 优先用项目名判断厚度
        if re.search(r"1\.2mm", nn):
            return {
                "material_main": 22.5,
                "material_loss_rate": 0.0,
                "material_aux": 6.0,
                "labor": 18.0,
                "machinery": 0.5,
            }, "[实际样本]1.2mm JS防水层"
        elif re.search(r"聚氨酯", nn) and re.search(r"2\s*mm", text) and not re.search(r"上翻|翻边|立面", nn):
            return {
                "material_main": 32.0,
                "material_loss_rate": 0.0,
                "material_aux": 8.0,
                "labor": 28.0,
                "machinery": 0.0,
            }, "[市场参考]2mm聚氨酯防水(单层,上翻另列)"
        elif re.search(r"2mm|3mm|4mm", nn) or re.search(r"JS防水", nn):
            return {
                "material_main": 30.0,
                "material_loss_rate": 0.0,
                "material_aux": 12.0,
                "labor": 42.0,
                "machinery": 0.5,
            }, "[实际样本]2mm JS防水层"
        elif re.search(r"立面|聚氨酯", nn):
            # 2mm 单层聚氨酯（上翻另列）与立面含上翻不是同一口径：
            # 单层 2mm 主材32/人工28；立面含翻边才走 35/19.85。
            if re.search(r"2\s*mm", text) and not re.search(r"上翻|翻边|立面", nn):
                return {
                    "material_main": 32.0,
                    "material_loss_rate": 0.0,
                    "material_aux": 8.0,
                    "labor": 28.0,
                    "machinery": 0.0,
                }, "[市场参考]2mm聚氨酯防水(单层,上翻另列)"
            return {
                "material_main": 35.0,
                "material_loss_rate": 0.0,
                "material_aux": 8.0,
                "labor": 19.85,
                "machinery": 0.5,
            }, "[实际样本]立面防水层(聚氨酯防水)"
        # 项目名无厚度信息时，用完整文本(text)判断
        elif re.search(r"1\.2mm.*防水|1\.2mm.*JS", text):
            return {
                "material_main": 22.5,
                "material_loss_rate": 0.0,
                "material_aux": 6.0,
                "labor": 18.0,
                "machinery": 0.5,
            }, "[实际样本]1.2mm JS防水层(特征)"
        elif re.search(r"聚氨酯", text) and re.search(r"2\s*mm", text) and not re.search(r"上翻|翻边", text):
            return {
                "material_main": 32.0,
                "material_loss_rate": 0.0,
                "material_aux": 8.0,
                "labor": 28.0,
                "machinery": 0.0,
            }, "[市场参考]2mm聚氨酯防水(单层,上翻另列)"
        elif re.search(r"JS防水|2mm.*防水", text):
            return {
                "material_main": 30.0,
                "material_loss_rate": 0.0,
                "material_aux": 12.0,
                "labor": 42.0,
                "machinery": 0.5,
            }, "[实际样本]2mm JS防水层(特征)"
        elif re.search(r"聚氨酯.*防水|防水.*聚氨酯", text):
            if re.search(r"2\s*mm", text) and not re.search(r"上翻|翻边", text):
                return {
                    "material_main": 32.0,
                    "material_loss_rate": 0.0,
                    "material_aux": 8.0,
                    "labor": 28.0,
                    "machinery": 0.0,
                }, "[市场参考]2mm聚氨酯防水(单层,上翻另列)"
            return {
                "material_main": 35.0,
                "material_loss_rate": 0.0,
                "material_aux": 8.0,
                "labor": 19.85,
                "machinery": 0.5,
            }, "[实际样本]立面防水层(聚氨酯防水)(特征)"
    # 卫生纸架/纸巾架（含镜后纸巾架等组合产品）
    # 金标准：卫生纸架 主材181.74 辅材11.65 人工34.95 机械4.66（合价233.0）
    #         镜后纸巾架二合一 主材235.17 辅材15.08 人工45.22 机械6.03（合价301.5）
    if unit_n in ("个", "套") and re.search(r"卫生纸架|纸巾架|镜后纸巾架", text):
        if re.search(r"二合一|感应皂液器|镜后", text):
            return {
                "material_main": 235.17,
                "material_loss_rate": 0.0,
                "material_aux": 15.08,
                "labor": 45.22,
                "machinery": 6.03,
            }, "[实际样本]镜后纸巾架二合一"
        else:
            # 金标准价格：主材181.74, 辅材11.65, 人工34.95, 机械4.66
            return {
                "material_main": 181.74,
                "material_loss_rate": 0.0,
                "material_aux": 11.65,
                "labor": 34.95,
                "machinery": 4.66,
            }, "[金标准]卫生纸架"
    return None, ""


def lookup_mirror_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """镜子/背发光镜零散成品。"""
    nn = normalize_name(name)
    text = normalize_name(f"{name}\n{feature}")
    unit_n = normalize_unit(unit)
    if "镜" not in text:
        return None, ""
    explicit_mirror_install = bool(re.search(r"镜子安装|成品.*镜|镜面玻璃|银镜", nn))
    if re.search(r"湿贴|人造石|石材", text) or (
        "墙面" in text and not explicit_mirror_install
    ):
        return None, ""
    if unit_n in ("个", "套") and re.search(r"背发光镜|发光镜|发光.*镜", text):
        return {
            "material_main": 308.0,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 116.0,
            "machinery": 1.4,
        }, "[市场参考]背发光镜子"
    if unit_n in ("m2", "㎡") and re.search(r"镜子安装|成品.*镜|镜面玻璃|银镜$", nn):
        # 实际样本校准：卫生间镜面玻璃实_主材0,实_人工45
        if re.search(r"卫生间镜面玻璃|浴室镜面玻璃", text):
            return {
                "material_main": 0.0,
                "material_loss_rate": 0.0,
                "material_aux": 0.0,
                "labor": 45.0,
                "machinery": 0.0,
            }, "[市场参考]卫生间镜面玻璃（主材利旧）"
        return {
            "material_main": 100.0,
            "material_loss_rate": 0.0,
            "material_aux": 15.0,
            "labor": 55.0,
            "machinery": 0.0,
        }, "[市场参考]卫生间镜子安装"
    return None, ""


def lookup_parking_stop_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """停车位车档/车轮定位器。"""
    text = normalize_name(f"{name}\n{feature}")
    if not re.search(r"停车位车档|车轮定位器|车档.*安装", text):
        return None, ""
    if normalize_unit(unit) not in ("对", "组", "套", "个"):
        return None, ""
    return {
        "material_main": 110.0,
        "material_loss_rate": 0.0,
        "material_aux": 0.0,
        "labor": 27.03,
        "machinery": 1.5,
    }, "[市场参考]室外停车位车档"


def lookup_misc_install_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """低风险零散安装/措施项，保持参考价口径。"""
    nn = normalize_name(name)
    unit_n = normalize_unit(unit)
    if unit_n in ("项",) and re.fullmatch(r"脚手架费用", nn):
        return {
            "material_main": 200378.4,
            "material_loss_rate": 0.0,
            "material_aux": 100189.2,
            "labor": 190359.48,
            "machinery": 10018.92,
        }, "[复核参考]脚手架措施费包干，需按项目措施清单确认"
    if unit_n in ("项",) and re.search(r"消防工程.*验收.*系统接入.*放水|验收.*系统接入.*放水", nn):
        return {
            "material_main": 0.0,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 42500.0,
            "machinery": 0.0,
        }, "[复核参考]消防验收/系统接入/放水包干人工，需按项目措施清单确认"
    if unit_n in ("组", "套", "个") and re.fullmatch(r"货架安装", nn):
        return {
            "material_main": 100.0,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 26.67,
            "machinery": 3.2,
        }, "[市场参考]货架安装"
    if unit_n in ("m", "米") and re.search(r"提升门钢结构框架.*方钢管", nn):
        return {
            "material_main": 40.0,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 33.7,
            "machinery": 25.0,
        }, "[市场参考]提升门钢结构框架"
    if unit_n in ("kg", "千克") and re.search(r"管道支架.*刷油|支架.*刷油", nn):
        return {
            "material_main": 6.87,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 5.77,
            "machinery": 1.21,
        }, "[市场参考]管道支架刷油"
    if unit_n in ("m2", "㎡") and re.search(r"室外杂草清理|杂草清理", nn):
        return {
            "material_main": 0.0,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 4.21,
            "machinery": 0.12,
        }, "[市场参考]室外杂草清理"
    if unit_n in ("m2", "㎡") and re.fullmatch(r"系统的调试", nn):
        return {
            "material_main": 0.0,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 2.6,
            "machinery": 0.0,
        }, "[市场参考]系统调试按面积"
    if unit_n in ("m2", "㎡") and re.fullmatch(r"CFC保温", nn, re.I):
        return {
            "material_main": 0.0,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 28.0,
            "machinery": 0.0,
        }, "[市场参考]CFC保温人工补项"
    return None, ""


def lookup_loose_equipment_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """零散设备/灯具成品，避免落入 generic_finish。"""
    nn = normalize_name(name)
    unit_n = normalize_unit(unit)
    table = (
        (r"高功率条形灯", ("套", "个"), (146.7, 37.0, 33.44, 0.0), "高功率条形灯"),
        (r"室外路灯", ("套", "个", "台"), (1027.88, 11.58, 253.78, 114.22), "室外路灯"),
        (r"65寸电视|电视.*伸缩支架", ("台", "套"), (2850.0, 1.71, 63.7, 3.5), "65寸电视"),
        (r"8T专用硬盘|专用硬盘", ("块", "个"), (1070.8, 2.21, 218.4, 0.0), "专用硬盘"),
        (r"车牌识别道闸|道闸", ("台", "套"), (8500.69, 6.84, 82.4, 189.19), "车牌识别道闸"),
        (r"电磁炉", ("台", "个"), (650.0, 0.0, 150.0, 0.0), "电磁炉"),
        (r"雨水篦子", ("个", "套", "块"), (171.73, 15.46, 8.7, 0.0), "雨水篦子"),
        (r"灭火毯", ("m2", "㎡", "块"), (60.0, 0.0, 0.0, 0.0), "灭火毯"),
    )
    for pat, units, comps, label in table:
        if unit_n in units and re.search(pat, nn, re.I):
            main, aux, labor, mach = comps
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[市场参考]{label}"
    return None, ""


def lookup_loose_furniture_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """柜体/层板等没有尺寸历史时的审价参考。"""
    nn = normalize_name(name)
    unit_n = normalize_unit(unit)
    table = (
        (r"木饰面层板", ("个", "块"), (150.0, 35.0, 60.0, 0.3), "木饰面层板"),
        (r"垃圾桶柜", ("个", "套"), (1230.0, 0.0, 150.0, 0.0), "垃圾桶柜"),
        (r"收纳柜", ("m2", "㎡"), (1280.0, 51.0, 35.0, 1.5), "收纳柜"),
        (r"浴室柜", ("个", "套"), (1050.0, 35.0, 150.0, 1.5), "浴室柜"),
        (r"清洁间门", ("m2", "㎡"), (1250.0, 27.0, 145.0, 1.5), "清洁间门"),
        (r"硬木夹板门|房间门", ("m2", "㎡"), (476.19, 2.0, 80.0, 0.0), "硬木夹板门"),
        (r"金属踢脚线T6", ("m2", "㎡"), (212.75, 30.03, 130.0, 0.0), "金属踢脚线T6"),
    )
    for pat, units, comps, label in table:
        if unit_n in units and re.search(pat, nn, re.I):
            main, aux, labor, mach = comps
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[市场参考]{label}"
    return None, ""


def lookup_civil_misc_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """小市政/土建零星项，非包干费用不自动填。"""
    nn = normalize_name(name)
    unit_n = normalize_unit(unit)
    table = (
        (r"150mm素混凝土基层|素混凝土基层", ("m2", "㎡"), (76.83, 0.0, 5.28, 0.14), "素混凝土基层"),
        (r"结构楼板加固", ("m2", "㎡"), (400.0, 0.0, 74.69, 1.5), "结构楼板加固"),
        (r"水泥混凝土路面", ("m2", "㎡"), (83.68, 0.0, 12.69, 0.27), "水泥混凝土路面"),
        (r"网状围栏", ("m2", "㎡"), (185.0, 25.0, 35.0, 15.0), "网状围栏"),
        (r"卫生间回填", ("m3", "m³", "立方", "立方米"), (385.0, 12.0, 85.0, 0.0), "卫生间回填"),
        (r"圈梁|水平系梁|导墙", ("m3", "m³", "立方", "立方米"), (1044.42, 0.0, 375.87, 19.32), "圈梁/水平系梁/导墙"),
    )
    for pat, units, comps, label in table:
        if unit_n in units and re.search(pat, nn):
            main, aux, labor, mach = comps
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[市场参考]{label}"
    return None, ""


def lookup_loose_material_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """明确名称的纯材料小项，不带安装人工。"""
    nn = normalize_name(name)
    unit_n = normalize_unit(unit)
    table = (
        (r"安全扶手", ("个", "套"), 15.0, "安全扶手"),
        (r"石膏板", ("张", "块"), 31.0, "石膏板"),
        (r"石膏板凹槽条", ("m", "米"), 3.0, "石膏板凹槽条"),
        (r"C型多功能槽钢", ("m", "米"), 10.9, "C型多功能槽钢"),
        (r"勾缝剂", ("吨", "t"), 2300.0, "勾缝剂"),
        # 审计校准：合页 实_主材25.0（个，纯材料不带安装）
        (r"合页|铰链", ("个", "只", "副", "套"), 25.0, "合页"),
        # 审计校准：晾衣杆 实_主材70.0（m，成品杆）
        (r"晾衣杆|晾衣架", ("m", "米"), 70.0, "晾衣杆"),
    )
    for pat, units, main, label in table:
        if unit_n in units and re.fullmatch(pat, nn, re.I):
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": 0.0,
                "labor": 0.0,
                "machinery": 0.0,
            }, f"[市场参考]纯材料-{label}"
    return None, ""


def lookup_frosted_film_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """玻璃磨砂贴膜：名称可能是「墙纸裱糊」等泛名，特征含磨砂纸/贴膜才命中
    （福永修缮实证：玻璃窗贴磨砂纸被材料价库 glass 品类误给 267/m²）。"""
    text = f"{name}\n{feature or ''}"
    if "磨砂" not in text or not re.search(r"磨砂纸|磨砂膜|贴膜", text):
        return None, ""
    return {
        "material_main": 18.0, "material_loss_rate": 0.05,
        "material_aux": 2.0, "labor": 8.0, "machinery": 0.0,
    }, "[磨砂贴膜]玻璃磨砂纸（含铺贴）"


def lookup_leb_box_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """等电位联结箱 LEB/总等电位：小箱体，勿吃材料价库 electrical_device
    的配电箱价（福永实证 1002/台 vs 控制价 56~154）。"""
    text = f"{name}\n{feature or ''}"
    if "等电位" not in text:
        return None, ""
    if re.search(r"接地母线|接地端子|测试板安装", name):
        return None, ""
    return {
        "material_main": 85.0, "material_loss_rate": 0.0,
        "material_aux": 5.0, "labor": 35.0, "machinery": 0.0,
    }, "[电气]等电位联结箱（含安装）"


def lookup_special_line_components(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """定稿口径优先项（可打断历史弱匹配）。"""
    for fn in (
        lookup_frosted_film_components,
        lookup_leb_box_components,
        lookup_ceiling_opening_components,
        lookup_ceiling_slot_components,
        lookup_curtain_box_components,
        lookup_light_slot_linear_components,
        lookup_stone_arc_guard_components,
        lookup_washbasin_counter_components,
        lookup_epoxy_floor_skirting_components,
        lookup_haide_basement_pt_paint_components,
        lookup_parking_line_marking_components,
        lookup_public_tile_components,
        lookup_tile_skirting_components,
        lookup_hand_painted_mural_components,
        lookup_review_priority_small_item_components,
        lookup_finish_exact_components,
        lookup_stainless_wrap_components,
        lookup_sanitary_accessory_extra_components,
    ):
        comps, note = fn(name, feature, unit)
        if comps:
            return comps, note
    return None, ""


def lookup_misc_finish_fallback(
    name: str, feature: str, unit: str
) -> Tuple[Optional[dict], str]:
    """零散成品/饰面兜底（仅历史不够强时）。"""
    for fn in (
        lookup_plant_pot_components,
        lookup_insulation_panel_components,
        lookup_color_steel_partition_components,
        lookup_roll_door_components,
        lookup_stainless_wrap_components,
        lookup_copper_bar_components,
        lookup_sanitary_accessory_extra_components,
        lookup_mirror_components,
        lookup_parking_stop_components,
        lookup_misc_install_components,
        lookup_loose_equipment_components,
        lookup_loose_furniture_components,
        lookup_civil_misc_components,
        lookup_loose_material_components,
    ):
        comps, note = fn(name, feature, unit)
        if comps:
            return comps, note
    return None, ""
