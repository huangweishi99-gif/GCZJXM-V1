# -*- coding: utf-8 -*-
"""多联机/内机型号价（会所安装 SWJ/SNJ 代号）。"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from src.normalize.text import normalize_name, normalize_unit


def _parse_model_num(name: str, prefix: str) -> Optional[int]:
    m = re.search(rf"{prefix}-(\d+(?:\.\d+)?)", name, re.I)
    if not m:
        return None
    try:
        return int(float(m.group(1)))
    except ValueError:
        return None


def lookup_vrf_hvac_components(
    name: str,
    feature: str = "",
    unit: str = "",
) -> Tuple[Optional[dict], str]:
    """多联外机 SWJ / 内机 SNJ / 一拖一内机。"""
    unit_n = normalize_unit(unit)
    if unit_n not in ("套", "台", "个", "件"):
        return None, ""
    text = normalize_name(f"{name}\n{feature}")

    if re.search(r"多联机.*室外机.*安装|室外机.*多联机.*安装", text):
        return {
            "material_main": 615.38,
            "material_loss_rate": 0.0,
            "material_aux": 307.69,
            "labor": 584.62,
            "machinery": 30.77,
        }, "[VRF外机安装] 多联机室外机安装"

    if re.search(r"多联外机|SWJ", text, re.I):
        cap = _parse_model_num(name, "SWJ") or 250
        main = round(5500 + cap * 38, 2)
        labor = round(620 + cap * 0.45, 2)
        aux = round(main * 0.04, 2)
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": aux,
            "labor": labor,
            "machinery": 25.0,
        }, f"[VRF外机 SWJ] 型号系数{cap}"

    # 多联式/变频多联 室外机：清单给"制冷量XXkW"时按冷量工程价
    # （实际样本校准：云湾 L-2 制冷量61.5kW → 主材25277.5=411元/kW、人工600/台）
    kw_m = re.search(r"制冷量[：:]?\s*(\d+(?:\.\d+)?)\s*[kK][wW]", text)
    if kw_m and re.search(r"室外机|外机", text):
        cap = float(kw_m.group(1))
        if cap >= 10:  # kW，排除小型一拖一外机
            main = round(cap * 411.0, 2)
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": round(main * 0.0034, 2),
                "labor": 600.0,
                "machinery": 10.5,
            }, f"[VRF多联外机 制冷量{cap}kW] 实际样本校准（411元/kW）"

    if re.search(r"内机|SNJ|风管机", text, re.I) and re.search(
        r"SNJ|一拖一|风管机", text, re.I
    ):
        if re.search(r"1\.0HP|1\.5HP|2\.0HP", text, re.I):
            hp_m = re.search(r"(\d+(?:\.\d+)?)\s*HP", text, re.I)
            hp = float(hp_m.group(1)) if hp_m else 1.0
            main = round(1800 + hp * 650, 2)
            labor = round(320 + hp * 40, 2)
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": round(main * 0.05, 2),
                "labor": labor,
                "machinery": 8.0,
            }, f"[VRF一拖一内机] {hp}HP"
        cap = _parse_model_num(name, "SNJ") or 25
        main = round(1400 + cap * 42, 2)
        labor = round(280 + cap * 1.8, 2)
        aux = round(main * 0.05, 2)
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": aux,
            "labor": labor,
            "machinery": 5.0,
        }, f"[VRF内机 SNJ] 型号系数{cap}"

    return None, ""


def lookup_fire_broadcast_components(
    name: str,
    feature: str = "",
    unit: str = "",
) -> Tuple[Optional[dict], str]:
    """消防应急广播主机/控制器。"""
    if normalize_unit(unit) not in ("套", "台", "个", "件"):
        return None, ""
    text = normalize_name(f"{name}\n{feature}")
    if not re.search(r"消防应急广播|广播主机|广播控制器", text):
        return None, ""
    if re.search(r"线缆|广播线|WDZN", text) and not re.search(r"主机|控制器", name):
        return None, ""
    return {
        "material_main": 3800.0,
        "material_loss_rate": 0.0,
        "material_aux": 180.0,
        "labor": 420.0,
        "machinery": 0.0,
    }, "[消防应急广播] 主机/控制器"


def lookup_sanitary_fixture_components(
    name: str,
    feature: str = "",
    unit: str = "",
) -> Tuple[Optional[dict], str]:
    """洁具单件（座→套 口径）。"""
    if normalize_unit(unit) not in ("套", "个", "组", "台"):
        return None, ""
    text = normalize_name(f"{name}\n{feature}")
    nn = normalize_name(name)
    if re.search(r"拆除", text):
        return None, ""
    # 接线盒属于电气附件，即使特征含"小便斗感应接线盒"等也不应套洁具价
    if "接线盒" in nn:
        return None, ""

    # 2026 审计校准：洁具配件前置排除（避免被台盆/拖把池/小便器等误伤）
    if "抓杆" in text or "扶手" in text:
        # 洗手盆抓杆 实_主材15, 实_人工0
        return {"material_main": 15.0, "material_aux": 0.0, "labor": 0.0,
                "machinery": 0.0, "material_loss_rate": 0.0}, "[洁具]抓杆扶手"
    if "开孔" in text or "开槽" in text:
        # 石材台面开洗菜盆孔 实_主材0, 实_人工35
        return {"material_main": 0.0, "material_aux": 0.0, "labor": 35.0,
                "machinery": 0.0, "material_loss_rate": 0.0}, "[洁具]台面开孔"
    if "隔断" in text:
        # 小便斗隔断 实_主材147.5-204, 实_人工50
        return {"material_main": 200.0, "material_aux": 8.0, "labor": 50.0,
                "machinery": 0.0, "material_loss_rate": 0.0}, "[洁具]隔断"
    if ("水龙头" in text or "水咀" in text) and not re.search(r"洗手盆|洗脸盆|台盆|水槽", text):
        # 拖把池水龙头/用水咀龙头 实_主材36, 实_人工20（整套盆+龙头不在内）
        return {"material_main": 36.0, "material_aux": 3.0, "labor": 20.0,
                "machinery": 0.0, "material_loss_rate": 0.0}, "[洁具]水龙头"

    if "小便器" in text or "小便斗" in text:
        return {
            "material_main": 480.0,
            "material_aux": 35.0,
            "labor": 85.0,
            "machinery": 0.0,
            "material_loss_rate": 0.0,
        }, "[洁具]小便器"
    if re.search(r"钢架", text) and re.search(r"台下盆|台盆", text):
        return {
            "material_main": 285.0,
            "material_aux": 0.0,
            "labor": 0.0,
            "machinery": 0.0,
            "material_loss_rate": 0.0,
        }, "[洁具]台下盆钢架"
    if "洗脸盆" in text or nn == "洗脸盆":
        # 2026 审计校准：独立洗脸盆 实_主材320, 实_人工55
        return {
            "material_main": 320.0,
            "material_aux": 12.0,
            "labor": 55.0,
            "machinery": 0.0,
            "material_loss_rate": 0.0,
        }, "[洁具]洗脸盆"
    if nn == "台盆" or re.search(r"^台盆$|洗手盆|台下盆", nn) or "台下盆" in text:
        # 审计校准：台盆/洗手盆 实_主材555-650, 实_人工90-136 → 550/90
        return {
            "material_main": 550.0,
            "material_aux": 12.0,
            "labor": 90.0,
            "machinery": 0.0,
            "material_loss_rate": 0.0,
        }, "[洁具]台盆"
    if "蹲便器" in text or nn == "蹲便器":
        return {
            "material_main": 491.0,
            "material_aux": 5.0,
            "labor": 100.0,
            "machinery": 0.0,
            "material_loss_rate": 0.0,
        }, "[洁具]蹲便器"
    if "大便器" in text or "坐便器" in text:
        # 2026 审计校准：大便器 实_主材352.0, 实_人工334.4, 实_辅材176（含法兰密封/给排水连接）
        return {
            "material_main": 352.0,
            "material_aux": 160.0,
            "labor": 310.0,
            "machinery": 15.0,
            "material_loss_rate": 0.0,
        }, "[洁具]大便器"
    if nn == "淋浴器" or "淋浴器" in nn:
        # 2026 审计校准：淋浴器 实_主材1050-1300, 实_人工85 → 取1100/90
        return {
            "material_main": 1100.0,
            "material_aux": 35.0,
            "labor": 90.0,
            "machinery": 0.0,
            "material_loss_rate": 0.0,
        }, "[洁具]淋浴器"
    # 排除"插座"等非热水器设备
    if "电热水器" in text or ("热水器" in text and "小厨宝" not in text and "插座" not in text):
        cap_m = re.search(r"(\d+)\s*L", text, re.I)
        liters = int(cap_m.group(1)) if cap_m else 60
        # 实际样本校准：60L main=1504.20, labor=126.29, 80L main=1804.20, labor=207.24
        # 主材：base=604.2, 每升15元；人工：base=30.29, 每升2.28元
        main = round(604.2 + liters * 15.0, 2)
        labor = round(30.29 + liters * 2.28, 2)
        # 机械费约为主材的0.8%
        mach = round(main * 0.008, 2)
        return {
            "material_main": main,
            "material_aux": 0.0,
            "labor": labor,
            "machinery": mach,
            "material_loss_rate": 0.0,
        }, f"[洁具]电热水器{liters}L"
    if "拖把池" in text:
        # 审计校准：不锈钢拖把池实_主材713, 实_人工85; 陶瓷拖把池实_主材350, 实_人工65
        if "不锈钢" in text:
            main, labor = 710.0, 85.0
        else:
            main, labor = 350.0, 65.0
        return {
            "material_main": main,
            "material_aux": 25.0,
            "labor": labor,
            "machinery": 0.0,
            "material_loss_rate": 0.0,
        }, "[洁具]拖把池"
    if "智能马桶" in text or nn == "智能马桶":
        # 2026 审计校准：智能马桶 实_主材3200, 实_人工100
        return {
            "material_main": 2800.0,
            "material_aux": 120.0,
            "labor": 100.0,
            "machinery": 0.0,
            "material_loss_rate": 0.0,
        }, "[洁具]智能马桶"
    if "小厨宝" in text or nn == "小厨宝":
        # 2026 审计校准：5-7L实353.98/119.89, 10L实486.73-759.41/119.89-136.19
        cap_m = re.search(r"(\d+)\s*L", text, re.I)
        liters = int(cap_m.group(1)) if cap_m else 6
        if liters <= 7:
            main, labor = 360.0, 120.0
        elif liters == 10 and "10L" in text:
            main, labor = 760.0, 136.0
        else:
            main, labor = 490.0, 120.0
        return {
            "material_main": main,
            "material_aux": 35.0,
            "labor": labor,
            "machinery": 0.0,
            "material_loss_rate": 0.0,
        }, f"[洁具]小厨宝{liters}L"
    if ("水槽" in text and "集水槽" not in text) or "单盆" in text or "台下盆" in text:
        if "单盆" in text:
            # 2026 审计校准：厨用单盆水槽 实_主材950, 实_人工55
            main, labor = 950.0, 60.0
        else:
            main, labor = 520.0, 95.0
        return {
            "material_main": main,
            "material_aux": 40.0,
            "labor": labor,
            "machinery": 0.0,
            "material_loss_rate": 0.0,
        }, "[洁具]水槽"
    if "手扳阀" in text or nn == "手扳阀":
        return {
            "material_main": 85.0,
            "material_aux": 8.0,
            "labor": 25.0,
            "machinery": 0.0,
            "material_loss_rate": 0.0,
        }, "[洁具]手扳阀"
    return None, ""


def _extract_wire_area(name: str, feature: str = "") -> Tuple[float, str]:
    """解析配线截面；多芯线按芯数×截面计算总截面。"""
    def _parse(spec: str) -> Tuple[float, str]:
        multi = re.search(r"(\d+)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(?:mm2|mm²)?", spec, re.I)
        if multi:
            cores = float(multi.group(1))
            section = float(multi.group(2))
            return cores * section, f"{int(cores):g}*{section:g}mm²"

        single = re.search(
            r"(?:BV|BVR|BYJ|RVV|RYS|RYJS|BLV|BVV)\s*-?\s*(?:B\d+\s*-?\s*)?(\d+(?:\.\d+)?)\s*(?:mm2|mm²)?",
            spec,
            re.I,
        ) or re.search(r"(\d+(?:\.\d+)?)\s*(?:mm2|mm²|mm)", spec, re.I)
        if single:
            section = float(single.group(1))
            return section, f"{section:g}mm²"
        return 0.0, ""

    # 名称中的完整型号比特征里的通用/默认规格更明确，不能被后者覆盖。
    name_area, name_note = _parse(name or "")
    if name_area > 0:
        return name_area, name_note

    raw = f"{name}\n{feature or ''}"
    label = re.search(r"(?:型号规格|型号、规格|型号|规格)\s*[:：]\s*([^\n\r；;,，]+)", raw, re.I)
    if label:
        label_area, label_note = _parse(label.group(1))
        if label_area > 0:
            return label_area, label_note

    raw_area, raw_note = _parse(raw)
    if raw_area > 0:
        return raw_area, raw_note
    return 0.0, ""


# 管内穿线定稿口径（会所合并清单-20260705）：截面mm² → (主材, 人工)
#   2.5→3.20/1.50  4→4.90/2.00  6→7.30/2.20  10→12.50/2.50  16→18.20/2.80（辅材0.18、机械1.14）
# 旧公式 125+area×1.4（约130~140元/m）取自旧版清单 20260701 异常行（各截面同值 139.09），已废弃。
_CONDUIT_WIRE_TABLE = (
    (2.5, 3.20, 1.50),
    (4.0, 4.90, 2.00),
    (6.0, 7.30, 2.20),
    (10.0, 12.50, 2.50),
    (16.0, 18.20, 2.80),
)


def _conduit_wire_components(area: float) -> dict:
    """管内穿线按定稿口径表线性插值（辅材、机械为定稿常值）。"""
    pts = _CONDUIT_WIRE_TABLE
    if area <= pts[0][0]:
        main, labor = pts[0][1], pts[0][2]
    elif area >= pts[-1][0]:
        x0, m0, l0 = pts[-2]
        x1, m1, l1 = pts[-1]
        k = (area - x1) / (x1 - x0)
        main = m1 + (m1 - m0) * k
        labor = l1 + (l1 - l0) * k
    else:
        main, labor = pts[-1][1], pts[-1][2]
        for (xa, ma, la), (xb, mb, lb) in zip(pts, pts[1:]):
            if xa <= area <= xb:
                r = (area - xa) / (xb - xa)
                main = ma + (mb - ma) * r
                labor = la + (lb - la) * r
                break
    return {
        "material_main": round(main, 2),
        "material_loss_rate": 0.02,
        "material_aux": 0.18,
        "labor": round(labor, 2),
        "machinery": 1.14,
    }


def lookup_hvac_duct_components(
    name: str,
    feature: str = "",
    unit: str = "",
) -> Tuple[Optional[dict], str]:
    """通风机/风管/百叶/冷媒管等。"""
    unit_n = normalize_unit(unit)
    text = normalize_name(f"{name}\n{feature}")

    # 冷冻水管含橡塑保温（价格较高）
    if unit_n in ("m", "米") and re.search(r"冷冻水管|冷冻水", text, re.I):
        dm = re.search(r"DN(\d{2,3})", text)
        dia = int(dm.group(1)) if dm else 80
        # 2026 审计校准：实主材≈12+DN×0.65，实人工≈5+DN×0.68，机械=主材×0.05
        #   DN20 实22.88/21.74/11.44/1.14；DN50 实44.44/42.22/22.22/2.22
        #   DN100 实77.44/73.57/38.72/3.87
        frozen_table = {
            20: (25.0, 21.5),
            25: (28.5, 26.0),
            32: (32.5, 30.0),
            40: (37.5, 35.0),
            50: (44.5, 42.0),
            65: (54.0, 52.0),
            80: (64.0, 61.0),
            100: (77.0, 73.0),
            150: (110.0, 95.0),
        }
        if dia in frozen_table:
            main, labor = frozen_table[dia]
            aux = round(main * 0.5, 2)
            return {
                "material_main": main,
                "material_loss_rate": 0.03,
                "material_aux": aux,
                "labor": labor,
                "machinery": round(main * 0.05, 2),
            }, f"[冷冻水管] DN{dia}含保温"

    if unit_n in ("m", "米") and re.search(r"冷媒铜管|铜管", text):
        dm = re.search(r"[Φφø]\s*(\d+(?:\.\d+)?)", text)
        has_symbol_dm = bool(dm)
        if not dm:
            dm = re.search(r"(\d+(?:\.\d+)?)\s*\*\s*(\d+(?:\.\d+)?)", text)
        if not dm:
            # 无Φ符号时从名称提取口径（允许 1 位小数，如"冷媒铜管 6.4"）
            dm = re.search(r"(?<!保温)(?<!层)(\d+(?:\.\d+)?)", name)
            # 无Φ符号、从名称提取到的小数，视为盘管/直管单价口径（2026 审计校准）
            from_name_dm = True
        else:
            from_name_dm = False
        dia = float(dm.group(1)) if dm else 15.9
        if dia > 100 and dia <= 500:
            dia = dia / 10.0
        # 2026 审计校准：
        # 带Φ符号（如 Φ6.35*0.75 含橡塑保温20mm）：
        #   Φ6.35 实14.85/11.88/2.97/0；Φ9.52 实19.25/15.4/3.85/0
        #   Φ28.6 实57.75/46.2/11.55/0；Φ31.8 实63.25/50.6/12.65/0
        #   Φ54 实101.75/81.4/20.35/0
        # 无Φ符号（名称"冷媒铜管 6.4"等，含保温，主材≈8.5×dia+45）：
        #   6.4→99.4/20.24/7.95/7.95；22.2→233.7/25.77/18.7/18.7
        has_insulation = re.search(r"保温|橡塑", text) or re.search(r"保温", feature)
        
        if not has_symbol_dm:
            # 无Φ符号：主材线性 8.5×dia+45（实际样本精确拟合）
            main = round(45.0 + dia * 8.5, 2)
            labor = round(15.0 + dia * 0.5, 2)
            aux = round(main * 0.08, 2)
            mach = round(main * 0.08, 2)
            return {
                "material_main": main,
                "material_loss_rate": 0.03,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[冷媒铜管] φ{dia}mm+保温（盘管口径）"
        
        # 带Φ符号：铜管本身价格（不含保温），2026 审计校准（Φ6.35实14.85, Φ12.7实24.75, Φ54实101.75）
        if dia <= 10:
            main = round(3.0 + dia * 1.2, 2)
        elif dia <= 15:
            main = round(4.0 + dia * 0.9, 2)
        elif dia <= 19:
            main = round(8.0 + dia * 0.85, 2)
        elif dia <= 23:
            main = round(10.0 + dia * 1.0, 2)
        elif dia <= 32:
            main = round(15.0 + dia * 1.0, 2)
        elif dia <= 54:
            main = round(8.0 + dia * 0.9, 2)
        else:
            main = round(25.0 + dia * 1.5, 2)
        
        # 保温成本（2026 校准：Φ28.6含保温实57.75，铜管≈36.7→保温≈21）
        if has_insulation:
            insulation_cost = round(dia * 0.75 + 0.5, 2)
            main = main + insulation_cost
        
        # 人工（2026 校准：Φ6.35实11.88, Φ19.05实28.6, Φ54实81.4 → 全部≈dia×1.5）
        labor = round(dia * 1.5, 2)
        
        # 辅材≈主材20%（实14.85→2.97, 19.25→3.85, 57.75→11.55），机械=0（实样本均0）
        aux = round(main * 0.2, 2)
        mach = 0.0
        return {
            "material_main": main,
            "material_loss_rate": 0.03,
            "material_aux": aux,
            "labor": labor,
            "machinery": mach,
        }, f"[冷媒铜管] φ{dia}mm{'+保温' if has_insulation else ''}"

    if unit_n in ("m", "米") and re.search(
        r"配线|BV-|BYJ|RVV|RVS|RYS|RYJS|WDZBN|WDZN|WDZC|WDZ|WDZB|ZR-BV", text, re.I
    ) and not re.search(r"配管|电线管", text, re.I) and not re.search(r"YJV|YJLV|电力电缆", text, re.I):
        area, note = _extract_wire_area(name, feature)
        if area <= 0:
            area = 2.5
            note = "2.5mm²"
        is_hf_cable = re.search(r"WDZC|WDZN|WDZBN|WDZ|WDZB|NH-RYJS", text, re.I) and not re.search(r"JHS", text, re.I)
        if re.search(r"RVV", text, re.I):
            # RVV多芯护套线：区分2芯与5+芯，人工与芯数相关而非截面
            # 金标准：RVV-2*0.75 主材2.65/人工1.86；RVV-2*1.0 主材2.92/人工1.73；RVV-2*2.5 主材5.98/人工1.73
            #         RVV-5*1.0 主材8.86/人工7.27；RVV-7*0.75 主材9.90/人工7.27；RVV-7*1.5 主材18.56/人工7.27
            core_match = re.search(r"RVV\D*(\d+)\s*[x×*]", text, re.I)
            cores = int(core_match.group(1)) if core_match else 2
            if cores <= 2:
                main = round(1.0 + area * 1.0, 2)
                labor = 1.73
            else:
                main = round(1.0 + area * 1.7, 2)
                labor = 7.27
            aux = round(main * 0.04, 2)
            mach = round(main * 0.007, 2)
            return {
                "material_main": main,
                "material_loss_rate": 0.02,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[配线] RVV {note}"
        elif re.search(r"RYJSP|RYSP", text, re.I):
            # RYJSP低烟无卤屏蔽双绞线
            # 实际样本：WDZBN-RYJSP-2x1.5实_主材3.09,实_人工4.28（area=3）
            main = round(0.8 + area * 0.7, 2)
            labor = round(2.0 + area * 0.8, 2)
        elif re.search(r"RVS|RYS|RYJS", text, re.I):
            # RVS/RYJS低烟无卤双绞线：
            # RVS（ZR-RVS）：聚氯乙烯绝缘绞型连接用软线
            # RYS：聚乙烯绝缘绞型软线
            # RYJS：低烟无卤聚乙烯绝缘绞型软线
            # 实际样本：
            # WDZBN-RYJS-2x1.5实_主材3.09,实_人工4.28（area=3）
            # 报警信号二线WDZN-RYS-B2-2X2.5mm2实_主材4.84,实_人工1.84（area=5）
            # 消防工程ZR-RVS 2*1.5实_主材2.25,实_人工2.4（area=3）
            if re.search(r"消防", text, re.I) and re.search(r"ZR-RVS|ZR-RV", text, re.I):
                # 消防工程ZR-RVS线缆（聚氯乙烯绝缘绞型连接用软线）
                main = round(0.6 + area * 0.55, 2)
                labor = round(0.8 + area * 0.53, 2)
            elif re.search(r"报警信号|信号二线", text, re.I):
                # 报警信号线人工较低，辅材和机械与主材相当
                # 实际样本：报警信号二线WDZN-RYS-B2-2X2.5mm2实_主材4.84,实_辅材1.65,实_人工1.84,实_机械1.65（area=5）
                main = round(0.8 + area * 0.81, 2)
                labor = round(0.8 + area * 0.21, 2)
                aux = round(main * 0.34, 2)  # 辅材约为主材34%
                mach = round(main * 0.34, 2)  # 机械费约为主材34%
                return {
                    "material_main": main,
                    "material_loss_rate": 0.02,
                    "material_aux": aux,
                    "labor": labor,
                    "machinery": mach,
                }, f"[配线] 报警信号线 {note}"
            else:
                # RYS/RYJS/WDZBN-RYJS等低烟无卤线缆
                main = round(0.8 + area * 0.75, 2)
                labor = round(2.0 + area * 0.8, 2)
        elif re.search(r"JHS", text, re.I):
            # JHS防水橡套电缆，价格较低（实际样本WDZBN-JHS-2x2.5: main=4.84, labor=1.84，area=5）
            main = round(0.8 + area * 0.8, 2)
            labor = round(0.8 + area * 0.2, 2)
        elif is_hf_cable:
            is_conduit = re.search(r"管内穿线|(?<!配)穿线", text)  # 使用负向后瞻排除"配线"中的"线"
            is_trunking = re.search(r"线槽配线", text)
            if is_conduit and area <= 16:
                # 管内穿线走定稿口径表（旧公式 125+area×1.4 已废弃）
                return _conduit_wire_components(area), f"[配线] 管内穿线 {note}"
            if area <= 2.5:
                # 实际样本：WDZBN-BYJ-1.5实_主材1.98,实_人工1.84（area=1.5）
                # 之前公式：main=1.5+1.5*1.2=3.30，偏高
                main = round(0.8 + area * 0.85, 2)
                labor = round(1.2 + area * 0.4, 2)
            elif area <= 6:
                if is_trunking:
                    # 线槽配线WDZC-BYJ-6：主材38, 人工22
                    main = round(30.0 + area * 1.3, 2)
                    labor = round(20.0 + area * 0.3, 2)
                else:
                    # 实际样本：WDZ-BYJ-6实_主材4.94,实_人工1.64；WDZB-BYJ-4实_主材3.49,实_人工1.23
                    main = round(1.5 + area * 0.7, 2)
                    labor = round(1.0 + area * 0.11, 2)
            elif area <= 10:
                # 实际样本：普通WDZ-BYJ-10约8-10元（管内穿线走定稿口径表）
                if is_trunking:
                    # 线槽配线WDZC-BYJ-10：主材约50-60, 人工约25
                    main = round(45.0 + area * 1.5, 2)
                    labor = round(22.0 + area * 0.3, 2)
                else:
                    # 普通WDZ-BYJ-10：主材约8-10元/m
                    main = round(3.0 + area * 0.9, 2)
                    labor = round(1.5 + area * 0.15, 2)
            elif area <= 16:
                main = round(5.0 + area * 0.8, 2)
                labor = round(2.0 + area * 0.2, 2)
            else:
                main = round(area * 1.5, 2)
                labor = round(3.0 + area * 0.3, 2)
        else:
            # 普通BV线（ZR-BV等）/ BVR多股软线
            # 实际样本：配线ZR-BV-10实_主材8.21,实_人工1.84；ZR-BV-4实_主材4.01,实_人工1.41；ZRNH-BV-2.5实_主材2.81,实_人工1.43
            # 消防工程ZR-BVR 2.5: 实_主材2.25,实_人工2.4
            # 配线ZR-BV-2.5: 实_主材2.78,实_人工2.12
            # 配线ZR-BV-6: 实_主材4.94,实_人工1.64
            is_bvr = bool(re.search(r"BVR|BLV|BVV", text, re.I))
            if is_bvr and area <= 2.5:
                # BVR多股软线（ZR-BVR 2.5 电源线）：实_主材3.50,实_人工1.25,实_辅材0.25
                # 旧值 2.25/2.4 是误把 ZR-RVS 2*1.5 的样本套到这里
                main = round(0.5 + area * 1.20, 2)
                labor = round(0.75 + area * 0.20, 2)
            elif area <= 2.5:
                # ZR-BV-2.5实际样本：主材2.78, 人工2.12；ZR-BVR 2.5: 主材2.25, 人工2.4
                main = round(0.6 + area * 0.87, 2)
                labor = round(0.8 + area * 0.52, 2)
            elif area <= 6:
                main = round(1.2 + area * 0.62, 2)
                labor = round(1.0 + area * 0.10, 2)
            elif area <= 10:
                main = round(2.0 + area * 0.7, 2)
                labor = round(1.0 + area * 0.1, 2)
            elif area <= 16:
                main = round(3.0 + area * 0.6, 2)
                labor = round(1.2 + area * 0.15, 2)
            else:
                main = round(area * 1.2, 2)
                labor = round(1.5 + area * 0.2, 2)
        return {
            "material_main": main,
            "material_loss_rate": 0.02,
            "material_aux": round(0.15 + main * 0.02, 2),
            "labor": labor,
            "machinery": round(labor * 0.01, 2),
        }, f"[配线] {note}"

    if unit_n in ("㎡", "m2") and re.search(r"风管软接|帆布软接|防火帆布", text):
        # 实际样本校准：
        # 消防工程：主材19.49, 人工110.02, 辅材38.1, 机械2.75
        # 暖通工程：主材19.49, 人工43.32-71.32, 辅材59.4, 机械2.75
        is_fire_project = bool(re.search(r"消防", text))
        if is_fire_project:
            return {
                "material_main": 19.49,
                "material_loss_rate": 0.0,
                "material_aux": 38.1,
                "labor": 110.02,
                "machinery": 2.75,
            }, "[风管软接头] 防火帆布(消防工程)"
        else:
            # 暖通工程（暖通/通风）
            return {
                "material_main": 19.49,
                "material_loss_rate": 0.0,
                "material_aux": 59.4,
                "labor": 55.0,
                "machinery": 2.75,
            }, "[风管软接头] 防火帆布(暖通工程/审计校准)"

    # 拆除/移位类不套安装价（主材会虚高）：实际样本"镀锌风管拆除、移位"主0 人153.47 辅0 机3.13
    if re.search(r"拆除", text) and re.search(r"风管|风道|管道", text):
        if unit_n in ("㎡", "m2", "m", "米"):
            return {
                "material_main": 0.0,
                "material_loss_rate": 0.0,
                "material_aux": 0.0,
                "labor": 153.47,
                "machinery": 3.13,
            }, "[通风风管] 拆除/移位（仅人工）"
        return None, ""

    if unit_n in ("m", "米", "㎡", "m2") and re.search(
        r"排风风管|新风风管|镀锌风管|通风管道", text
    ):
        return {
            "material_main": 85.0,
            "material_loss_rate": 0.03,
            "material_aux": 12.0,
            "labor": 48.0,
            "machinery": 2.0,
        }, "[通风风管] 按延长米"

    if unit_n in ("m", "米") and re.search(r"线槽|桥架", name):
        wm = re.search(r"(\d+)\s*\*\s*(\d+)", text)
        width = int(wm.group(1)) if wm else 100
        height = int(wm.group(2)) if wm else 100
        # 名称/特征压平成单行后，序号会并进规格（"…200*100" + "1.型号" → "200*1001"），
        # 贪婪匹配会把 height 读成 1001（面积虚增 10 倍）。越界时按 2~3 位严格重解。
        if height > 400 or width > 1500:
            tight = re.search(r"(\d{2,4})\s*\*\s*(\d{2,3})", text)
            if tight:
                width, height = int(tight.group(1)), int(tight.group(2))
        # 桥架价格基于截面积（宽×高）
        area = width * height / 1000  # mm²/1000
        is_weak = re.search(r"弱电", text)
        is_fire = re.search(r"消防", text)
        is_steel = re.search(r"镀锌|钢制", text)
        
        # 根据实际样本校准（2026 重校准，主材按面积中位曲线）：
        # 桥架400*200*2.0：main=126.45, labor=100.33 → area=80
        # 镀锌桥架400*150*2.0：main=74.35, labor=58.35 → area=60
        #   实_辅材0, 实_机械2.36
        # 弱电桥架100*100：main=29.90, labor=24.57 → area=10
        # 弱电线槽100*50：main=6.00, labor=29.80 → area=5
        # 消防桥架100*50：main=20.23, labor=18.57 → area=5
        # 镀锌桥架50*50*1.0：main=16.61, labor=25.25 → area=2.5
        # 桥架(厚度1.2mm）50*100：main=24.54, labor=21.99 → area=5
        #   实_辅材3.58, 实_机械1.02
        # 镀锌桥架100*100*1.5：main=29.50, labor=30.00 → area=10
        #   实_辅材10.5, 实_机械0.5
        # 镀锌线槽100*100：main=25.00, labor=29.80 → area=10
        # 2026 审计校准（多项目均值）：
        #   100*100*1.5: main≈33.4, labor≈24.9 → area=10
        #   150*100*1.5: main≈37.9, labor≈38.4 → area=15
        #   200*100*1.5: main≈48.2, labor≈30.7 → area=20
        #   200*150*1.5: main≈54.2, labor≈44.8 → area=30
        #   300*100*1.5: main≈64.4, labor≈32.8 → area=30
        #   300*150*1.5: main≈66.9, labor≈51.5 → area=45
        #   500*200*1.5: main≈86.5, labor≈89.8 → area=100
        #   600*100*2.0: main≈136.5, labor≈100.3 → area=60
        
        # 桥架辅材和机械费（实际样本校准）
        # 镀锌桥架：辅材0，机械费约为主材的2-3%
        # 普通桥架：辅材按材质计算，机械费约0.5-1.0
        
        # 不锈钢线槽/小线槽不应按大尺寸桥架计价（500*200不锈钢线槽实main=38）
        if re.search(r"线槽", text) and re.search(r"不锈钢|铝合金|铝制", text):
            # 不锈钢/铝合金线槽：薄板弯折，价格低
            main = round(15.0 + area * 0.22, 2)  # 500*200→main≈37
            labor = round(15.0 + area * 0.06, 2)  # 500*200→labor≈21
            aux = 5.0
            mach = round(main * 0.02, 2)
        elif width >= 400:
            if is_steel and height == 150:
                # 实际样本：镀锌桥架400*150*2.0实_主材74.35,实_人工58.35
                main = 74.35
                labor = 58.35
                aux = 0.0  # 镀锌桥架辅材为0
                mach = round(main * 0.03, 2)  # 机械费约3%
            elif width >= 550:
                # 600*100*2.0：main≈136.5, labor≈100.3
                main = round(110.0 + area * 0.45, 2)
                labor = round(90.0 + area * 0.18, 2)
                aux = 0.0
                mach = round(main * 0.03, 2)
            elif width >= 450:
                # 500*200*1.5：main≈86.5-91.6, labor≈89.8-100.3
                main = round(55.0 + area * 0.32, 2)  # 100→87
                labor = round(70.0 + area * 0.25, 2)  # 100→95
                aux = 0.0
                mach = round(main * 0.03, 2)
            else:
                # 大尺寸桥架：400*200→main=126, labor=100
                main = round(50.0 + area * 0.95, 2)
                labor = round(45.0 + area * 0.7, 2)
                aux = 0.0
                mach = round(main * 0.03, 2)
        elif width >= 200:
            # 中尺寸桥架（2026 审计校准：镀锌300*100实64.43判57需加大截距）
            if is_steel:
                # 镀锌桥架 200*100: main≈48.2, labor≈30.7 → area=20
                # 镀锌桥架 200*150: main≈54.2, labor≈44.8 → area=30
                # 镀锌桥架 300*100: main≈64.4, labor≈32.8 → area=30
                # 镀锌桥架 300*150: main≈66.9, labor≈51.5 → area=45
                main = round(45.0 + area * 0.4, 2)
                labor = round(24.0 + area * 0.4, 2)
                aux = 0.0  # 实辅材多为0
                mach = round(main * 0.03, 2)
            else:
                # 非镀锌「金属桥架/普通桥架」200以上（会所精装修两版样本 + 弱电桥架）：
                #   金属桥架200*100 实 38/22 与 36.5/30 → 取 37/26（原 labor=38 偏高，两行皆判失败）
                #   弱电桥架200*100 实38.9/30.95、200*150 实48.1/30.95 → 同曲线
                main = round(25.0 + area * 0.6, 2)
                labor = round(15.0 + area * 0.55, 2)
                aux = 0.0
                mach = round(main * 0.02, 2)
        elif is_fire:
            # 消防桥架：100*50→main=20, labor=18
            main = round(15.0 + area * 1.0, 2)
            labor = round(15.0 + area * 0.7, 2)
            aux = 0.0
            mach = round(main * 0.02, 2)
        elif is_steel:
            # 镀锌/钢制桥架：50*50→main=16, labor=25; 100*100→main=29.5, labor=30
            # 桥架(厚度1.2mm）50*100: main=24.54, labor=21.99
            if width <= 50 and height <= 50:
                # 小尺寸镀锌桥架：50*50→main=16, labor=25
                main = round(8.0 + area * 3.2, 2)
                labor = round(18.0 + area * 2.5, 2)
                aux = 0.0
                mach = round(main * 0.02, 2)
            elif width <= 50 and height >= 100:
                # 50*100桥架（实际样本校准）
                main = round(18.0 + area * 1.3, 2)
                labor = round(15.0 + area * 1.4, 2)
                aux = 3.58  # 实际样本：桥架50*100辅材3.58
                mach = 1.02  # 实际样本：桥架50*100机械1.02
            elif width <= 100 and height <= 100:
                # 100*100 镀锌桥架/线槽（2026 审计校准：实25-33.4 → 取29.5）
                main = 29.5
                labor = 26.0
                aux = 0.0  # 镀锌桥架实辅材为0
                mach = 0.52  # 实际样本：镀锌线槽100*100机械0.52
            elif width >= 100 and height >= 100:
                # 150*100镀锌桥架（2026 校准）
                #   150*100*1.5: main≈37.9, labor≈38.4
                main = round(22.0 + area * 1.1, 2)  # 15→38.5
                labor = round(6.0 + area * 2.0, 2)  # 15→36
                aux = 0.0  # 镀锌桥架实辅材为0
                mach = 0.52  # 实际样本：镀锌线槽100*100机械0.52
            else:
                # 中尺寸镀锌桥架
                main = round(15.0 + area * 1.5, 2)
                labor = round(22.0 + area * 0.8, 2)
                aux = round(main * 0.12, 2)
                mach = 0.5
        elif is_weak and height <= 50:
            # 弱电小线槽（100*50等）：main=6, labor=30
            main = round(3.0 + area * 0.6, 2)
            labor = round(25.0 + area * 1.0, 2)
            aux = 0.70
            mach = 0.5
        elif is_weak:
            # 弱电桥架（100*100等）：main=30, labor=25
            main = round(15.0 + area * 1.5, 2)
            labor = round(20.0 + area * 0.45, 2)
            aux = 0.0
            mach = 0.5
        else:
            # 普通桥架/线槽（实际样本校准）
            # 桥架(厚度1.2mm）50*100: main=24.54, labor=21.99, aux=3.58, mach=1.02
            # 镀锌线槽100*100: main=25.00, labor=29.80, aux=8.56, mach=0.52
            if width <= 50 and height >= 100:
                # 50*100桥架（普通型）
                main = round(18.0 + area * 1.3, 2)
                labor = round(15.0 + area * 1.4, 2)
                aux = 3.58
                mach = 1.02
            elif width >= 100 and height >= 100:
                # 100*100线槽（2026 审计校准：普通桥架实34.15/镀锌线槽实25 → 取29.5/26）
                main = 29.5
                labor = 26.0
                aux = 8.56
                mach = 0.52
            else:
                main = round(18.0 + area * 1.5, 2)
                labor = round(18.0 + area * 0.8, 2)
                aux = 0.0
                mach = 0.5
        return {
            "material_main": main,
            "material_loss_rate": 0.02,
            "material_aux": aux,
            "labor": labor,
            "machinery": mach,
        }, f"[线槽] {'弱电' if is_weak else ''}{'消防' if is_fire else ''}{width}*{height}"

    if unit_n in ("套", "台", "个", "件") and re.search(
        r"通风机|通風机|EAF|PF-L|离心风机|直联.*风机|管道.*风机", text, re.I
    ):
        # 2026 审计校准：按风量分档（实际样本多档位校准）
        #   3000及以下: main=1352.92, labor=869.45
        #   3000-5000:  main=1991.15, labor=1000.45
        #   5000-8000:  main=2645.13, labor=1269.45（辅材104.89, 机械62.55）
        #   15000-20000: main=4940.71, labor=1496.04
        #   20000-25000: main=7610.62, labor=1496.04（辅材125.22, 机械62.55）
        #   20000-30000: main=10946.9, labor=1396.04
        # 保护性拆除：主材0, 人工279.73, 机械31.28
        is_dismantle = re.search(r"拆除|拆装", text)
        is_supplied = re.search(r"主材甲供|甲供|利旧", text)
        # 2026 审计校准：单数字风量（如"风量3000m³/h及以下"）也要能匹配
        volume_range = re.search(r"(\d{4,5})\s*[-~至]\s*(\d{4,5})", text)
        volume_single = re.search(r"风量\s*(\d{3,5})", text) or re.search(r"(\d{4,5})", text)
        if volume_range:
            max_v = max(int(volume_range.group(1)), int(volume_range.group(2)))
        elif volume_single:
            max_v = int(volume_single.group(1))
        else:
            max_v = 0
        if max_v == 0:
            main, labor = 2800.0, 380.0
        elif max_v <= 3000:
            main, labor = 1352.92, 869.45
        elif max_v <= 5000:
            main, labor = 1991.15, 1000.45
        elif max_v <= 8000:
            main, labor = 2645.13, 1269.45  # 实际样本校准
        elif max_v <= 20000:
            # 2026 审计校准：15000-20000 实4940.71/1496.04
            main, labor = 4940.71, 1496.04
        elif max_v <= 25000:
            main, labor = 7610.62, 1496.04
        else:
            main, labor = 10946.9, 1396.04
        if is_dismantle:
            main, aux = 0.0, 0.0
            labor = 279.73
            mach = 31.28
        else:
            aux = 104.89 if main <= 3000 else 125.22
            mach = 62.55
            if is_supplied:
                main = 0.0
                aux = 74.89
        return {
            "material_main": main,
            "material_aux": aux,
            "labor": labor,
            "machinery": mach,
        }, f"[通风机] 含安装"

    if unit_n in ("套", "台", "个", "件") and re.search(
        r"全热交换|新风换气|YCH", text, re.I
    ):
        return {
            "material_main": 8500.0,
            "material_aux": 280.0,
            "labor": 680.0,
            "machinery": 20.0,
        }, "[全热交换新风] 含安装"

    if unit_n in ("个", "套", "件") and re.search(r"防虫网|防虫网封堵", text):
        return {
            "material_main": 120.0,
            "material_aux": 15.0,
            "labor": 45.0,
            "machinery": 0.0,
        }, "[通风附件]防虫网封堵"

    if unit_n in ("个", "套", "件", "根", "只") and re.search(r"金属软接头|不锈钢软接头", text):
        # 2026 审计校准：金属软接头DN20 实_主材21.48,实_人工9.25（按管径分档）
        dm = re.search(r"DN\s*(\d{2,3})(?=\D|$)", text, re.I)
        dia = int(dm.group(1)) if dm else 20
        soft_joint_table = {
            15: (16.0, 7.0),
            20: (21.48, 9.25),
            25: (28.0, 12.0),
            32: (36.0, 15.0),
            40: (45.0, 18.0),
            50: (58.0, 22.0),
            65: (78.0, 28.0),
            80: (95.0, 34.0),
            100: (125.0, 42.0),
        }
        main, labor = soft_joint_table.get(dia, (21.48, 9.25))
        return {
            "material_main": main,
            "material_aux": round(main * 0.077, 2),
            "labor": labor,
            "machinery": round(main * 0.031, 2),
        }, f"[给排水]金属软接头DN{dia}"
    if unit_n in ("个", "套", "件", "根", "只") and re.search(
        r"百叶|风阀|软接头|静压箱", text
    ):
        # 常开百叶风口（消防联动型）：与 decorative_diffuser 同值，避免"常开百叶风 口"（空格）漏到通用百叶
        if "常开百叶" in text:
            total = 340.0
            main = round(total * 0.77, 2)
            labor = round(total * 0.18, 2)
            aux = round(total * 0.03, 2)
            mach = round(total * 0.02, 2)
            return {
                "material_main": main,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, "[风口]常开百叶风口（消防联动）"
        main = 185.0 if "静压箱" in text else 95.0
        labor = 65.0 if "静压箱" in text else 35.0
        return {
            "material_main": main,
            "material_aux": 8.0,
            "labor": labor,
            "machinery": 0.0,
        }, "[风口/风阀/附件]"

    if unit_n in ("个", "套", "件") and re.search(r"分歧器|FQ\d", text, re.I):
        # 按FQ型号分级定价（实际样本校准）
        fq_match = re.search(r"FQ(\d+)", text, re.I)
        fq_num = int(fq_match.group(1)) if fq_match else 4
        # 两类口径必须分开：
        #   ① 冷媒分歧器（R410/干燥过滤器式，理想汽车框架清单）：
        #      FQ01A/B 实30/24、FQ02 实38/30、FQ03 实76/60、FQ04 实118/94
        #   ② 本体安装式分歧器（会所空调工程，型号写作纯 FQ01/FQ02）：
        #      珠海会所精装修+会所清单两版一致 实420/85/辅25/机25
        if fq_match and not re.search(r"冷媒|R410|干燥", text, re.I):
            main, labor, aux, mach = 420.0, 85.0, 25.0, 25.0
        else:
            fq_table = {
                1: (30.0, 24.0),
                2: (38.0, 30.0),
                3: (76.0, 60.0),
                4: (118.0, 94.0),
            }
            main, labor = fq_table.get(fq_num, (94.1, 89.4))
            aux = round(main * 0.5, 2)
            mach = round(labor * 0.05, 2)
        return {
            "material_main": main,
            "material_aux": aux,
            "labor": labor,
            "machinery": mach,
        }, f"[VRF分歧器FQ{fq_num}]"

    if unit_n in ("个", "套", "件") and re.search(r"NKG1|定式控制器|时控开关", text):
        # 2026 审计校准：NKG1微电脑时控开关 实_主材37.87,实_人工28.81
        return {
            "material_main": 37.87,
            "material_aux": 0.0,
            "labor": 28.81,
            "machinery": 0.99,
        }, "[时控开关]NKG1"
    if unit_n in ("个", "套", "件") and re.search(r"集中控制器|CC52", text):
        return {
            "material_main": 1386.0,
            "material_aux": 693.0,
            "labor": 1317.0,
            "machinery": 0.0,
        }, "[集中控制器]CC52系列"
    if unit_n in ("个", "套", "件") and re.search(r"控制器", text):
        return {
            "material_main": 280.0,
            "material_aux": 15.0,
            "labor": 45.0,
            "machinery": 15.0,
        }, "[空调/风机控制器]"

    if unit_n in ("m", "米") and re.search(r"屏蔽线|手拉手", text):
        return {
            "material_main": 12.0,
            "material_aux": 2.0,
            "labor": 8.0,
            "machinery": 0.0,
        }, "[弱电]屏蔽线"

    if unit_n in ("m", "米", "根") and re.search(r"PVC装饰盖|装饰盖管", text):
        return {
            "material_main": 28.0,
            "material_aux": 3.0,
            "labor": 12.0,
            "machinery": 0.0,
        }, "[PVC装饰盖管]"

    if unit_n in ("套", "台", "个", "件") and re.search(r"冰箱|自助售卖|售卖机", text):
        main = 3200.0 if "冰箱" in text else 8500.0
        return {
            "material_main": main,
            "material_aux": round(main * 0.05, 2),
            "labor": round(main * 0.08, 2),
            "machinery": 0.0,
        }, "[设备]冰箱/售卖机"

    return None, ""


def lookup_fire_weak_components(
    name: str,
    feature: str = "",
    unit: str = "",
) -> Tuple[Optional[dict], str]:
    if normalize_unit(unit) not in ("套", "台", "个", "件"):
        return None, ""
    text = normalize_name(f"{name}\n{feature}")
    if re.search(r"火灾显示盘|区域型火灾报警|火灾报警控制器", text):
        return {
            "material_main": 2200.0,
            "material_aux": 80.0,
            "labor": 280.0,
            "machinery": 0.0,
        }, "[消防]报警显示/控制器"
    if re.search(r"信号报警阀", text):
        return {
            "material_main": 3401.53,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 301.88,
            "machinery": 45.51,
        }, "[消防]信号报警阀"
    if re.search(r"输入模块", text):
        return {
            "material_main": 52.65,
            "material_loss_rate": 0.0,
            "material_aux": 1.3,
            "labor": 116.75,
            "machinery": 0.6,
        }, "[消防弱电]输入模块"
    if re.search(r"短路隔离模块", text):
        main = 0.0 if "主材利旧" in text else 52.65
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": 1.23,
            "labor": 100.75,
            "machinery": 0.7,
        }, "[消防弱电]短路隔离模块"
    if re.search(r"天花喇叭", text):
        return {
            "material_main": 283.19,
            "material_loss_rate": 0.0,
            "material_aux": 0.86,
            "labor": 102.38,
            "machinery": 14.02,
        }, "[弱电广播]天花喇叭"
    if re.search(r"寻呼话筒", text):
        return {
            "material_main": 1022.12,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 22.75,
            "machinery": 0.27,
        }, "[弱电广播]寻呼话筒"
    if re.search(r"应急广播扬声器|广播扬声器", text):
        return {
            "material_main": 180.0,
            "material_aux": 12.0,
            "labor": 35.0,
            "machinery": 0.0,
        }, "[消防]广播扬声器"
    if re.search(r"声光报警|声光警报|火灾声光", text):
        main = 0.0 if "主材利旧" in text else 165.0
        labor = 86.0 if "主材利旧" in text else 60.0
        aux = 1.0 if "主材利旧" in text else 10.0
        return {
            "material_main": main,
            "material_aux": aux,
            "labor": labor,
            "machinery": 0.0,
        }, "[消防]声光报警器"
    return None, ""


def lookup_mep_accessory_components(
    name: str,
    feature: str = "",
    unit: str = "",
) -> Tuple[Optional[dict], str]:
    """零散机电附件：金属软管、配线架、水表等。"""
    unit_n = normalize_unit(unit)
    text = normalize_name(f"{name}\n{feature}")

    # 线性灯（EL01/EL02 电梯墙面线性灯等）也走灯带功率分级，2026审计校准
    if unit_n in ("m", "米") and re.search(r"LED灯带|灯带|线性灯", text):
        power_match = re.search(r"(\d+)\s*W", text)
        power = int(power_match.group(1)) if power_match else 12
        # LED灯带价格较高（按功率分级，根据实际样本校准）
        # 实际样本：LED硬灯条 main=40, labor=18; 软灯带 main=23.5, labor=8; 侧弯灯带 main=35, labor=8
        is_hard_strip = re.search(r"硬灯条", text)
        is_soft_strip = re.search(r"软灯带", text)
        is_side_bend = re.search(r"侧弯|正弯", text)
        is_aluminum_base = re.search(r"铝基板", text)
        is_prism_guide = re.search(r"棱晶导光板|定制嵌装|墙面线性灯|造型线性灯", text)
        is_cob = re.search(r"COB", text, re.I)
        # 识别主材甲供情况
        is_material_supplied = re.search(r"主材甲供|甲供", text)
        
        if is_aluminum_base and re.search(r"DC\s*24V", text, re.I):
            # 深圳安装工程 LED灯带-SL01/SL01a/SL03（铝基板DC24V）2026审计校准
            # 实 main=14+0.5×W（SL01 14W→21.09, SL01a 10W→20.35, SL03 6W→19.61）, labor=5.5, aux=main×0.08
            main = round(14.0 + power * 0.5, 2)
            labor = 5.5
            mach = 0.0
        elif is_prism_guide:
            # 定制线性灯（棱晶导光板/压铸铝）PL01/PL01a/EL01/EL02 2026审计校准
            # 实 main=45+1.6×W（PL01 40W→112.11, PL01a/EL01 15W→78, EL02 10W→61）
            # 人工随功率：EL01 15W→21、EL02 10W→16.5（≈6+W/米），40W 档 28
            main = round(45.0 + power * 1.6, 2)
            labor = 28.0 if power >= 30 else round(6.0 + power, 2)
            mach = 0.0
        elif is_cob:
            # COB灯带（深圳）：含铝型材 main=48, 软灯带 main=16.09, 人工统一18.2（2026审计校准）
            main = 48.0 if re.search(r"铝型材", text) else 16.09
            labor = 18.2
            mach = 0.0
        elif is_side_bend:
            # 侧弯/正弯灯带（珠海会所Lc/Lr系列）2026审计校准：主材35/人工8/辅材0.5/机械0.5
            main = 35.0
            labor = 8.0
            mach = 0.5
        elif is_hard_strip:
            # 硬灯条价格较高
            main = round(25.0 + power * 1.25, 2)
            labor = round(10.0 + power * 0.8, 2)
            mach = 0.0
        elif is_soft_strip:
            # 软灯带价格较低
            main = round(12.0 + power * 0.95, 2)
            labor = round(4.0 + power * 0.35, 2)
            mach = 0.0
        elif power <= 12:
            # 2026 审计校准：12W灯带 实23.5/12, 墙面灯箱12W 实27.55/15.42 → 判23.6/12.5
            main = round(14.0 + power * 0.8, 2)
            labor = 12.5
            mach = 0.0
        elif power <= 24:
            # 2026 审计校准：15W灯带 甲供实(0,11.9) → 人工4+0.53×15≈12命中
            main = round(20.0 + power * 1.0, 2)
            labor = round(4.0 + power * 0.53, 2)
            mach = 0.0
        else:
            main = round(30.0 + power * 2.0, 2)
            labor = round(12.0 + power * 0.8, 2)
            mach = 0.0
        
        # 主材甲供时，主材价格为0，但保留人工
        if is_material_supplied:
            main = 0.0
        
        aux_ratio = 0.08 if (is_aluminum_base or is_prism_guide or is_cob) else 0.02
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": round(main * aux_ratio, 2),
            "labor": labor,
            "machinery": mach,
        }, f"[LED灯带] {power}W/m{'(主材甲供)' if is_material_supplied else ''}"

    if unit_n in ("组", "套", "个") and "末端试水装置" in text:
        main = 0.0 if "主材利旧" in text else 185.44
        labor = 140.62 if "主材利旧" in text else 128.41
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": 5.46,
            "labor": labor,
            "machinery": 1.25,
        }, "[给排水]末端试水装置DN25"

    if unit_n in ("个", "只", "套") and re.search(r"闸阀|截止阀|止回阀|恒温阀|自动排气阀", text):
        dm = re.search(r"DN\s*(\d{2,3})(?=\D|$)", text, re.I)
        dia = int(dm.group(1)) if dm else 0
        valve_table = {
            ("闸阀", 20): (18.56, 6.86, 22.75, 1.84),
            ("截止阀", 20): (22.60, 15.00, 25.00, 1.00),
            ("止回阀", 65): (216.09, 13.51, 66.51, 16.99),
            ("止回阀", 100): (334.41, 32.81, 162.96, 45.21),
            ("恒温阀", 15): (31.87, 2.00, 13.73, 1.00),  # 实际样本校准
            # 2026 审计校准：自动排气阀人工普遍偏低（DN20实6-26, DN32实27-30, 利旧DN25实37）
            #   DN15 实26-47主/6.5-11人；DN20 实47-61主/6-26人；DN32 实64-71主/27-30人
            ("自动排气阀", 15): (41.08, 3.16, 9.00, 1.26),  # 实际样本校准
            ("自动排气阀", 20): (55.00, 2.00, 15.00, 1.00),
            ("自动排气阀", 25): (50.00, 2.00, 20.00, 1.00),
            ("自动排气阀", 32): (68.00, 2.00, 29.00, 1.00),  # 实际样本校准
        }
        for valve_name in ("闸阀", "截止阀", "止回阀", "恒温阀", "自动排气阀"):
            values = valve_table.get((valve_name, dia))
            if valve_name in text and values:
                main, aux, labor, machine = values
                return {
                    "material_main": main,
                    "material_loss_rate": 0.0,
                    "material_aux": aux,
                    "labor": labor,
                    "machinery": machine,
                }, f"[给排水]阀门{valve_name}DN{dia}"

    # --- 2026-09 分流：机械开孔/孔槽（安装配合工种，按孔径档纯人工计，主材为 0）---
    # 审计样本：瓷砖/木基层等为地漏/开关插座盒/孔位机械开孔 方形≤100/圆Φ≤100 实_人工5/个
    if unit_n in ("个", "只", "套") and "机械开孔" in text and re.search(r"机械开孔[^\n]*?(100|100\s*以内|Φ\s*100|φ\s*100)", text):
        return {
            "material_main": 0.0,
            "material_aux": 0.0,
            "labor": 5.0,
            "machinery": 0.0,
            "material_loss_rate": 0.0,
        }, "[开孔]机械开孔100内"

    # --- 2026-09 分流：暗装底盒（开关/插座盒），不是面板，误套整套面板价会高估 ---
    # 审计样本：开关（插座）盒 钢制/塑料 暗装 实_主材7.5 实_人工3.0
    if unit_n in ("个", "只", "套") and re.search(r"开关\s*[（(]\s*插座\s*[)）]\s*盒|开关盒|插座盒|底盒|暗盒", text) and "面板" not in text and not re.search(r"配电|配线|箱", text):
        return {
            "material_main": 7.5,
            "material_aux": 0.0,
            "labor": 3.0,
            "machinery": 0.0,
            "material_loss_rate": 0.0,
        }, "[电气]底盒"

    # 排除非电气开关（窗户自动开关器、无线开关器等）
    if unit_n in ("个", "只", "套") and re.search(r"开关", text) and re.search(r"窗户|窗", text):
        return None, ""
    # 工业风扇/排风扇含"开关及电源"字样，但实为风扇（审计校准：工业风扇φ600 实主354/人152）
    if unit_n in ("台", "个", "套") and re.search(r"工业风扇|排风扇|风扇|换气扇", text):
        return None, ""
    # 洁具（感应一体小便器特征含"感应开关"等）不是电气面板，放行到洁具单件价
    if unit_n in ("个", "只", "套") and re.search(r"开关|插座", text) and not re.search(
        r"空调|地暖|智能|窗户|窗控|小便器|小便斗|大便器|坐便器|洗手盆|洗脸盆|洗面盆|台盆|马桶|蹲便|水槽|洗涤盆|拖把池|浴缸|浴盆|淋浴|花洒|水龙头|感应一体", text
    ):
        # 开关插座定价（实际样本校准）
        # 安全型二三孔插座(高端型,电气工程): 实_主材112.19, 实_人工86.72, 实_辅材0.0, 实_机械1.52
        # 安全型二三孔插座(低价型,强电工程): 实_主材17.09, 实_人工17.79
        # 三联单控开关: 实_主材87.68, 实_人工80.21, 实_辅材0.0, 实_机械1.28
        # 单联双控开关: 实_主材13.54, 实_人工12.97, 实_辅材0.68, 实_机械0.0
        # 单联单控暗开关: 实_主材45.00, 实_人工35.00
        # 套单位（含底盒）: 实_主材14.62, 实_人工6.31, 实_辅材1.12（多个项目复核）
        # 个单位普通插座: 实_主材15.0-20.0, 实_人工10.0
        
        # 根据特征区分高端型和低价型安全型插座
        is_high_end = bool(re.search(r"电气工程", text))
        is_set_unit = unit_n in ("套",)
        
        if "插座" in text and "地面" in text:
            # 地面插座（地插：预埋底盒+金属盖板）单列，不能按普通「套」档 14.62/6.31
            # 样本：珠海海德会所 8821 实125/25、8989 实97.83/42.13（同总价拆分不同）、会所合并 135/12
            # 取中位 125/25
            main, labor, aux, mach = 125.00, 25.00, 0.5, 0.5
        elif is_set_unit:
            # 套单位（含底盒+面板）：单价更低
            if "安全型" in text or "五孔" in text or "二三孔" in text:
                main, labor, aux, mach = 14.62, 6.31, 1.12, 0.0
            elif "三联" in text and "开关" in text:
                main, labor, aux, mach = 20.00, 12.00, 1.50, 0.0
            elif "双联" in text and "开关" in text:
                main, labor, aux, mach = 18.00, 10.00, 1.50, 0.0
            elif "单联" in text and "开关" in text:
                main, labor, aux, mach = 14.62, 6.31, 1.12, 0.0
            elif "开关" in text:
                main, labor, aux, mach = 14.62, 6.31, 1.12, 0.0
            else:
                main, labor, aux, mach = 14.62, 6.31, 1.12, 0.0
        elif "暗开关" in text:
            # 审计校准：暗装开关（会所曜岩灰）实_主材45.00, 实_人工35.00
            main, labor, aux, mach = 45.00, 35.00, 3.00, 3.00
        elif "防爆" in text:
            # 审计校准：防爆插座(工业/防爆型) 实_主材197.19, 实_人工101.0
            # 防爆开关 实_主材106.16, 实_人工56.95
            if "插座" in text:
                main, labor, aux, mach = 197.19, 101.00, 0.0, 1.52
            else:
                main, labor, aux, mach = 106.16, 56.95, 0.0, 1.39
        elif re.search(r"防水|防潮", text) and "插座" in text:
            # 2026 审计校准：防水插座实_主材15, 实_人工10（多项目样本，非高端）
            main, labor, aux, mach = 15.00, 10.00, 1.00, 0.0
        elif "防溅" in text and "插座" in text:
            # 审计校准：五孔防溅插座 实_主材29.5, 实_人工12
            main, labor, aux, mach = 30.00, 12.00, 1.00, 0.0
        elif re.search(r"16A|20A|16安|20安", text) and "插座" in text and re.search(
            r"烘手器|热水器|饮水机|即热|速热|烤箱|洗衣机|洗碗机|消毒柜|电磁炉|电陶炉|充电桩|柜机|大功率|空调插座", text
        ):
            # 审计校准：16A/20A 大功率插座（烘手器/热水器/大功率设备）实_主材127-138, 实_人工83-92
            # 仅限大功率设备语境；普通"三孔插座16A"面板按普通三孔档，避免把百元级全包价套在几元面板上
            main, labor, aux, mach = 130.00, 88.00, 0.0, 1.24
        elif "USB" in text and "插座" in text:
            # 2026 审计校准：五孔插座带USB+type C 实_主材78-85.8, 实_人工13
            main, labor, aux, mach = 85.00, 14.00, 0.0, 1.52
        elif "绕线器" in text and "插座" in text:
            # 审计校准：绕线器安全型二三孔插座 实_主材148.31, 实_人工50.69
            main, labor, aux, mach = 148.31, 50.69, 0.0, 1.52
        elif "地面" in text and "插座" in text:
            # 会所合并清单-20260705 定稿：五孔地面插座 实_主材135.0,实_人工12.0,实_辅材0.5,实_机械0.5
            main, labor, aux, mach = 135.00, 12.00, 0.5, 0.5
        elif "安全型" in text and ("二三孔" in text or "五孔" in text):
            if is_high_end:
                # 高端型：来自电气工程
                main, labor, aux, mach = 112.19, 86.72, 0.0, 1.52
            else:
                # 2026 审计校准：普通安全型二三孔 实_主材14.86-17.09, 实_人工15.47-17.79
                main, labor, aux, mach = 16.50, 17.00, 1.51, 0.0
        elif "四联" in text and "开关" in text:
            if is_high_end:
                # 审计校准：四联单控(电气工程) 实_主材93.11, 实_人工75.56
                main, labor, aux, mach = 93.11, 75.56, 0.0, 1.29
            else:
                # 审计校准：四联单控(强电) 实_主材16.25, 实_人工14.95
                main, labor, aux, mach = 16.25, 14.95, 0.0, 1.2
        elif "三联" in text and "开关" in text:
            # 审计校准：普通三联单控开关 实_主材17.00,实_人工13.65；高端（电气工程）实87.68/80.21
            if is_high_end:
                main, labor, aux, mach = 87.68, 80.21, 0.0, 1.28
            else:
                main, labor, aux, mach = 17.00, 13.65, 0.0, 1.2
        elif "双联" in text and "开关" in text:
            if is_high_end:
                # 审计校准：双联单控(电气工程) 实_主材72.71, 实_人工85.48
                main, labor, aux, mach = 72.71, 85.48, 0.0, 1.55
            else:
                # 审计校准：双联单控(强电) 实_主材14.44, 实_人工13.56
                main, labor, aux, mach = 14.44, 13.56, 0.0, 1.2
        elif "单联" in text and "双控" in text:
            if is_high_end:
                # 审计校准：单联双控(电气工程) 实_主材44.59-59.13, 实_人工103-117
                main, labor, aux, mach = 52.00, 110.00, 0.0, 1.27
            else:
                main, labor, aux, mach = 13.54, 12.97, 0.68, 0.0
        elif "单联" in text and "暗" in text:
            main, labor, aux, mach = 45.00, 35.00, 3.00, 3.00
        elif "单联" in text and "开关" in text:
            if is_high_end:
                # 审计校准：单联单控(电气工程) 实_主材41.23-48.66, 实_人工98-105
                main, labor, aux, mach = 45.00, 100.00, 0.0, 1.25
            else:
                # 审计校准：普通单联单控 实_主材13.54-17.0, 实_人工10-15
                main, labor, aux, mach = 15.00, 13.00, 0.0, 1.0
        elif "四孔" in text:
            # 2026 审计校准：三相四孔插座 实_主材21.86-25.14, 实_人工15.47-17.79
            main, labor, aux, mach = 24.00, 17.00, 1.00, 0.0
        elif "三孔" in text:
            if "设备" in text:
                # 审计校准：设备三孔插座 实_主材48.92-170.61, 实_人工25.5-31.1
                main, labor, aux, mach = 110.00, 28.00, 0.0, 0.86
            elif is_high_end:
                main, labor, aux, mach = 112.19, 86.72, 0.0, 1.52
            else:
                # 审计校准：普通三孔 实_主材14.86-17.09, 实_人工15.47-17.79
                main, labor, aux, mach = 16.00, 16.50, 1.00, 0.0
        elif "电视" in text and "插座" in text:
            # 2026 审计校准：电视机电源插座 实_主材96.52, 实_人工111.07
            main, labor, aux, mach = 96.50, 110.00, 0.0, 1.0
        elif "五孔" in text or "二三孔" in text or "电源" in text:
            if is_high_end:
                if re.search(r"16A|20A", text):
                    # 审计校准：16A/20A 电源插座(电气工程) 实_主材127-138, 实_人工83-92
                    main, labor, aux, mach = 130.00, 88.00, 0.0, 1.24
                else:
                    main, labor, aux, mach = 112.19, 86.72, 0.0, 1.52
            else:
                # 审计校准：普通五孔 实_主材12.0-15.0, 实_人工10-15
                main, labor, aux, mach = 13.50, 12.00, 1.00, 0.0
        elif "信息插座" in text:
            # 审计校准：弱电信息插座 单口实20.8/11.38, 双口实28.9/13.65
            if "单口" in text:
                main, labor, aux, mach = 21.00, 11.50, 0.0, 0.0
            elif "双口" in text:
                main, labor, aux, mach = 29.00, 13.70, 0.0, 0.0
            else:
                main, labor, aux, mach = 20.00, 11.00, 0.0, 0.0
        elif "多功能插座" in text:
            # 审计校准：多功能插座(弱电) 实_主材102.9, 实_人工12.97
            main, labor, aux, mach = 103.00, 13.00, 2.40, 0.0
        elif "防爆开关" in text:
            # 审计校准：防爆开关(电气工程) 实_主材106.16, 实_人工56.95
            main, labor, aux, mach = 106.16, 56.95, 0.0, 1.39
        elif "时控开关" in text:
            # 审计校准：时控开关(电气工程) 实_主材65.98, 实_人工34.88
            main, labor, aux, mach = 66.00, 35.00, 0.0, 1.45
        elif "光感开关" in text:
            # 审计校准：光感开关(电气工程) 实_主材71.81, 实_人工82.86
            main, labor, aux, mach = 72.00, 83.00, 0.0, 1.69
        elif "网络" in text and "插座" in text:
            main, labor, aux, mach = 20.00, 10.00, 0.0, 0.0
        elif "插座" in text:
            main, labor, aux, mach = 15.00, 10.00, 1.00, 0.0
        elif "开关" in text:
            # 2026 审计校准：普通开关 实_主材17-22, 实_人工10-15 → 取18/12
            main, labor, aux, mach = 18.00, 12.00, 0.0, 1.0
        else:
            main, labor, aux, mach = 20.00, 15.00, 0.50, 0.5
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": aux,
            "labor": labor,
            "machinery": mach,
        }, f"[电气]{'开关' if '开关' in text else '插座'}"

    if unit_n in ("个", "台", "套") and re.fullmatch(r"移位配电箱", normalize_name(name)):
        return {
            "material_main": 88.89,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 408.26,
            "machinery": 5.01,
        }, "[电气]移位配电箱"

    if unit_n in ("系统", "项") and re.search(r"通风工程.*检测.*调试|通风.*检测.*调试", text):
        return {
            "material_main": 400.0,
            "material_loss_rate": 0.0,
            "material_aux": 200.0,
            "labor": 380.0,
            "machinery": 20.0,
        }, "[通风调试]检测调试系统"

    if unit_n in ("台", "个", "套") and re.search(r"配电箱|配电柜", text) and not re.search(r"移位配电箱", text):
        if re.search(r"落地式|落地", text):
            # 实际样本：落地式配电箱实_主材8637.4,实_辅材36.96,实_人工524.73,实_机械18.91
            main = 8637.4
            labor = 524.73
            aux = round(main * 0.0043, 2)  # 辅材约为主材0.43%
            mach = round(main * 0.0022, 2)  # 机械费约为主材0.22%
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, "[电气]落地式成套配电箱"
        return None, ""

    if unit_n in ("台", "个", "套") and "智能电表" in text and not re.search(r"配电箱|配电柜", text):
        # 2026 审计校准：智能电表 实_主材116.81, 实_人工250.25
        return {
            "material_main": 116.81,
            "material_loss_rate": 0.0,
            "material_aux": 1.22,
            "labor": 250.25,
            "machinery": 0.0,
        }, "[电气]智能电表"

    if unit_n in ("台", "个", "套") and re.search(r"吸顶式房间通风器|房间通风器", text):
        main = 0.0 if "主材利旧" in text else 180.0
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": 5.9,
            "labor": 82.81,
            "machinery": 0.0,
        }, "[通风器]吸顶式房间通风器"

    if unit_n in ("套", "个") and re.search(r"七氟丙烷.*70L|70L.*七氟丙烷", text, re.I):
        return {
            "material_main": 3359.29,
            "material_loss_rate": 0.0,
            "material_aux": 20.76,
            "labor": 402.55,
            "machinery": 0.0,
        }, "[气体灭火]七氟丙烷70L"

    if unit_n in ("m", "米") and "金属软管" in text and not re.search(r"灯|条形|灯具|射灯|吊灯|吸顶灯", text):
        dm = re.search(r"DN\s*(\d{2,3})(?=\D|$)", text, re.I)
        dia = int(dm.group(1)) if dm else 20
        if re.search(r"含配件", text):
            # 深圳/岁宝等「增加金属软管￠16（含配件）」实_主材4.18/人工3.96/辅材2.09/机械0.21
            # 与江门「配管 金属软管 Φ20」3.0/6.9 是不同做法，故以「含配件」窄条件隔离
            return {
                "material_main": 4.18,
                "material_loss_rate": 0.0,
                "material_aux": 2.09,
                "labor": 3.96,
                "machinery": 0.21,
            }, "[金属软管]含配件Φ16"
        if dia <= 20:
            return {
                "material_main": 3.0,
                "material_loss_rate": 0.0,
                "material_aux": 1.11,
                "labor": 6.9,
                "machinery": 0.0,
            }, "[金属软管]DN20"
        if dia <= 25:
            return {
                "material_main": 3.2,
                "material_loss_rate": 0.0,
                "material_aux": 1.02,
                "labor": 8.0,
                "machinery": 0.0,
            }, "[金属软管]DN25"

    if unit_n in ("个", "台", "套") and "配线架" in text:
        pm = re.search(r"(\d{2})\s*口", text)
        ports = int(pm.group(1)) if pm else 24
        if ports >= 48:
            return {
                "material_main": 315.6,
                "material_loss_rate": 0.0,
                "material_aux": 0.0,
                "labor": 235.65,
                "machinery": 0.0,
            }, "[弱电]48口配线架"
        return {
            "material_main": 144.07,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 216.23,
            "machinery": 0.0,
        }, "[弱电]24口配线架"

    if unit_n in ("个", "套", "块", "只") and "水表" in text:
        dm = re.search(r"DN\s*(\d{2,3})(?=\D|$)", text, re.I)
        dia = int(dm.group(1)) if dm else 40
        # 实际样本校准：
        # 普通水表DN40实_主材131.27,实_人工72.80（来自给排水工程）
        # 特殊水表DN40（碳钢机械式）实_主材350.0,实_人工50.0（来自公区，消防局认可）
        is_special = bool(re.search(r"碳钢|机械式|消防局|认可", text))
        water_meter_table = {
            15: (60.0, 25.0),
            20: (87.53, 40.95),  # 2026 审计校准：DN20实主87.53/人工40.95
            25: (100.0, 40.0),
            32: (105.02, 59.15),  # 2026 审计校准：DN32实主105.02/人工59.15
            40: (131.27, 72.80),
            50: (180.0, 90.0),
            65: (318.58, 136.5),
            80: (398.23, 182.0),
            100: (502.94, 273.0),
            150: (776.68, 364.0),
        }
        # 特殊水表（碳钢机械式等）价格更高，辅材和机械费更低
        if is_special:
            special_table = {
                15: (120.0, 30.0),
                20: (150.0, 35.0),
                25: (200.0, 40.0),
                40: (350.0, 50.0),  # 实际样本校准：实_主材350,实_人工50,实_辅材1.5,实_机械0.0
                50: (450.0, 60.0),
                80: (600.0, 80.0),
                100: (800.0, 100.0),
            }
            main, labor = special_table.get(dia, (350.0, 50.0))
            aux = 1.5  # 特殊水表辅材低
            mach = 0.0  # 特殊水表机械费为0
        else:
            main, labor = water_meter_table.get(dia, (180.0, 50.0))
            aux = round(main * 0.055, 2)
            mach = round(main * 0.004, 2)
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": aux,
            "labor": labor,
            "machinery": mach,
        }, f"[给排水]水表DN{dia}{'（特殊）' if is_special else ''}"

    # Y型过滤器（实际样本：Y型过滤器DN25实_主材67.04,实_辅材9.14,实_人工25.03,实_机械2.25）
    if unit_n in ("个", "套", "只") and re.search(r"Y型过滤器|Y型过滤|过滤器", text):
        dm = re.search(r"DN\s*(\d{2,3})(?=\D|$)", text, re.I)
        dia = int(dm.group(1)) if dm else 25
        # 2026 审计校准（主材/人工随管径增大）：
        # DN20实主16.63-35.84/人工7.16-7.78；DN40实82.19/45.05
        # DN50实103.01/61.43；DN65实155.47/86.51；DN80实198.28/117.46
        # DN100实273.96/122.96；DN150实436.23/129.88
        y_filter_table = {
            15: (25.0, 7.0),
            20: (25.0, 7.0),
            25: (67.04, 25.03),
            32: (70.0, 30.0),
            40: (82.0, 45.0),
            50: (103.0, 61.0),
            65: (155.0, 86.0),
            80: (200.0, 117.0),
            100: (280.0, 122.0),
            150: (436.0, 130.0),
        }
        main, labor = y_filter_table.get(dia, (80.0, 30.0))
        aux_table = {20: 1.3, 25: 9.14, 32: 7.6, 40: 24.0, 50: 13.5, 65: 13.5, 80: 20.0, 100: 33.0, 150: 41.0}
        mach_table = {20: 0.5, 25: 2.25, 32: 3.0, 40: 3.5, 50: 4.5, 65: 17.0, 80: 18.0, 100: 45.0, 150: 97.0}
        return {
            "material_main": main,
            "material_loss_rate": 0.0,
            "material_aux": aux_table.get(dia, round(main * 0.12, 2)),
            "labor": labor,
            "machinery": mach_table.get(dia, round(labor * 0.08, 2)),
        }, f"[给排水]Y型过滤器DN{dia}"

    # 钢塑复合管（实际样本：钢塑复合管DN100实_主材40.30,实_辅材0.97,实_人工82.38,实_机械16.93）
    if unit_n in ("m", "米") and re.search(r"钢塑复合管|钢塑管", text):
        dm = re.search(r"DN\s*(\d{2,3})(?=\D|$)", text, re.I)
        dia = int(dm.group(1)) if dm else 100
        steel_plastic_table = {
            20: (3.2, 42.1),
            25: (3.2, 46.2),
            32: (5.5, 52.6),
            40: (11.1, 53.19),
            50: (12.19, 64.31),
            65: (25.1, 66.88),
            80: (38.0, 70.0),
            100: (40.30, 82.38),
            150: (93.0, 89.38),
        }
        main, labor = steel_plastic_table.get(dia, (35.0, 50.0))
        return {
            "material_main": main,
            "material_loss_rate": 0.02,
            "material_aux": round(main * 0.024, 2),
            "labor": labor,
            "machinery": round(labor * 0.205, 2),
        }, f"[给排水]钢塑复合管DN{dia}"

    # 离心玻璃棉保温（实际样本：离心玻璃棉保温通风管道80mm实_主材364.88,实_人工468.65,实_机械0）
    if unit_n in ("m3", "m³", "立方米") and re.search(r"离心玻璃棉|玻璃棉保温", text):
        # 厚度匹配
        thickness_match = re.search(r"(\d+)\s*mm", text)
        thickness = int(thickness_match.group(1)) if thickness_match else 50
        # 2026 审计校准：主材统一364.88，人工随厚度递减
        #   30mm→1058.79, 40mm→925.7, 50mm→792.84, 60mm→659.75, 70mm→535.31, 80mm→468.65
        if thickness >= 80:
            labor = 468.65
        elif thickness >= 70:
            labor = 535.31
        elif thickness >= 60:
            labor = 659.75
        elif thickness >= 50:
            labor = 792.84
        elif thickness >= 40:
            labor = 925.7
        else:
            labor = 1058.79
        return {
            "material_main": 364.88,
            "material_loss_rate": 0.05,
            "material_aux": round(364.88 * 0.11, 2),  # 实际辅材约39.32
            "labor": labor,
            "machinery": 0.0,  # 实际机械费为0
        }, f"[保温]离心玻璃棉{thickness}mm"

    # 橡塑保温通风管道（实际样本校准）
    # 橡塑保温通风管道30mm: 实_主材936.64, 实_人工947.31, 实_辅材51.26, 实_机械0
    # 橡塑保温通风管道50mm: 实_主材约1200, 实_人工约1200
    # 橡塑保温通风管道80mm: 实_主材约1800, 实_人工约1800
    if unit_n in ("m3", "m³", "立方米") and re.search(r"橡塑保温|橡塑.*保温", text):
        thickness_match = re.search(r"(\d+)\s*mm", text)
        thickness = int(thickness_match.group(1)) if thickness_match else 30
        # 2026 审计校准：10mm实(936.64,1340.42)，30mm实(936.64,947.31)
        if thickness >= 80:
            main, labor = 1800.0, 1800.0
        elif thickness >= 50:
            main, labor = 1200.0, 1200.0
        elif thickness >= 40:
            main, labor = 1000.0, 1000.0
        elif thickness <= 10:
            main, labor = 936.64, 1340.42
        else:
            main, labor = 936.64, 947.31
        return {
            "material_main": main,
            "material_loss_rate": 0.05,
            "material_aux": round(main * 0.055, 2),  # 实际辅材约5.5%
            "labor": labor,
            "machinery": 0.0,  # 实际机械费为0
        }, f"[保温]橡塑保温{thickness}mm"

    # 给排水接入市政管线（实际样本校准）
    # DN100: 主材90.0, 人工29.5
    # DN150: 主材100.0, 人工52.57
    # DN200: 主材110.0, 人工56.08
    if unit_n in ("m", "米") and re.search(r"市政管线|给排水接入", text):
        dm = re.search(r"DN\s*(\d{2,3})(?=\D|$)", text, re.I)
        dia = int(dm.group(1)) if dm else 150
        municipal_table = {
            100: (90.0, 29.5),
            150: (100.0, 52.57),
            200: (110.0, 56.08),
        }
        main, labor = municipal_table.get(dia, (100.0, 52.57))
        return {
            "material_main": main,
            "material_loss_rate": 0.03,
            "material_aux": 0.0,
            "labor": labor,
            "machinery": 0.5,
        }, f"[给排水]市政管线DN{dia}"

    return None, ""


def lookup_power_cable_components(
    name: str,
    feature: str = "",
    unit: str = "",
) -> Tuple[Optional[dict], str]:
    """电力电缆按导体截面汇总计价（YJV 铜芯 / YJLV 铝芯）。"""
    unit_n = normalize_unit(unit)
    if unit_n not in ("m", "米"):
        return None, ""
    text = normalize_name(f"{name}\n{feature}")
    if not re.search(r"电缆|YJV|YJLV", text, re.I):
        return None, ""
    # 只有项目名称本身是电缆头/终端/附件时才排除
    # 特征中包含"电缆头制作安装"等不应排除电缆本身
    if re.search(r"^电缆头|^电缆终端|^电缆附件", name):
        return None, ""

    spec = _extract_power_cable_spec(name, feature)
    total_mm2 = _sum_cable_core_area(spec)
    if total_mm2 <= 0:
        return None, ""

    is_al = bool(re.search(r"YJLV|铝芯", text, re.I))
    is_armored = bool(re.search(r"带铠|铠装", text, re.I))
    if is_al:
        # 铝芯电缆按总截面分层（实际样本校准）
        # YJLV-4×150+1×70(670mm²): main=81.52, rate≈0.122
        # YJLV-4×120+1×70(550mm²): main=65.88, rate≈0.12
        # YJLV-4×95+1×50(430mm²): main=56.79, rate≈0.132
        # YJLV-4×50+1×25(225mm²): main=44, rate≈0.196
        if total_mm2 <= 100:
            rate = 0.22
        elif total_mm2 <= 300:
            rate = 0.18
        elif total_mm2 <= 600:
            rate = 0.12
        else:
            rate = 0.12
    else:
        # 铜芯电缆：根据总截面和结构定rate（实际样本校准）
        # 检测电缆结构模式
        core_sizes = []
        for n_core, sect in re.findall(r"(\d+)\*(\d+(?:\.\d+)?)", spec or "", re.I):
            core_sizes.append((int(n_core), float(sect)))
        
        # 判断结构类型：4大+1小 / 3大+2小 / 等芯
        structure_type = "unknown"
        main_core_mm2 = 0.0
        if len(core_sizes) == 2:
            (n1, s1), (n2, s2) = core_sizes
            main_core_mm2 = max(float(s1), float(s2))
            if n1 == 4 and n2 == 1:
                structure_type = "4大+1小"
            elif n1 == 1 and n2 == 4:
                structure_type = "4大+1小"
            elif n1 == 3 and n2 == 2:
                structure_type = "3大+2小"
            elif n1 == 2 and n2 == 3:
                structure_type = "3大+2小"
            elif n1 == 5 or n2 == 5:
                structure_type = "5等芯"
        elif len(core_sizes) == 1:
            n_core, sect = core_sizes[0]
            main_core_mm2 = float(sect)
            if n_core == 5:
                structure_type = "5等芯"
        
        if total_mm2 <= 95:
            # 小截面电缆（实际样本校准，rate 随主芯截面变化）
            # YJV-5*2.5(total=12.5): 实18.88, rate≈1.51
            # YJV-3*2.5(total=7.5): 实9.9, rate≈1.32
            # YJV-5*4(total=20): 实18.66, rate≈0.93
            # YJV-5*6(total=30): 实25.94, rate≈0.86
            # YJV-5*16(total=80): 实56.17, rate≈0.70
            if structure_type == "5等芯" and main_core_mm2 >= 16:
                rate = 0.75
            elif main_core_mm2 <= 2.5:
                rate = 1.60
            elif main_core_mm2 <= 4:
                rate = 1.00
            elif main_core_mm2 <= 6:
                rate = 1.00
            elif main_core_mm2 <= 10:
                rate = 0.88
            else:
                rate = 0.92
        elif total_mm2 <= 150:
            # 中小截面（2026 审计校准：深海/开市客多项目 rate≈0.70）
            #   4*25+1*16 total=116: 实73.54/86.76, rate≈0.63-0.75
            #   3*35+2*16 total=137: 实99.38, rate≈0.73
            #   4*35+1*16 total=156: 实112.21, rate≈0.72
            rate = 0.70
        elif total_mm2 <= 300:
            # 中截面电缆（2026 审计校准：统一 rate≈0.70 命中率最高）
            #   ZR-3*50+2*25 total=200: 实156.36/139.09, rate≈0.70-0.78
            #   4*50+1*25 total=225: 实154.12, rate≈0.69
            #   3*70+2*35 total=280: 实196.8/165.01/243.76, rate≈0.59-0.87
            #   4*70+1*35 total=315: 实220.31, rate≈0.70
            rate = 0.70
        elif total_mm2 <= 600:
            # 中大截面电缆（2026 审计校准：多项目 rate 均≈0.70）
            #   WDZA-4*120+1*70 total=550: 实385.94, rate≈0.70
            #   WDZB-4*95+1*50 total=430: 实302.28, rate≈0.70
            #   3*120+2*70 total=500: 实350.6, rate≈0.70
            rate = 0.70
        else:
            # 大截面电缆（2026 审计校准：rate≈0.70）
            #   WDZB-3*240+2*120 total=960: 实676.29, rate≈0.70
            #   YJV-4*240+1*120 total=1080: 实803.66, rate≈0.74
            #   4*185+1*95 total=835: 实584.59, rate≈0.70
            rate = 0.70
    
    # 特殊校准：小截面电缆单价更高
    # 实际样本：YJV-5*6实_主材60.52，total_mm2=30，rate≈2.02
    # YJV-5*10实_主材40.53，total_mm2=50，rate≈0.81
    main_core_mm2 = 0.0
    for n_core, sect in re.findall(r"(\d+)\*(\d+(?:\.\d+)?)", spec or "", re.I):
        main_core_mm2 = max(main_core_mm2, float(sect))
    
    if main_core_mm2 <= 2.5:
        # 2026 校准：YJV-5*2.5 实18.88-22.76, rate≈1.5-1.8 → 取1.6
        rate = 1.60
    elif main_core_mm2 <= 4:
        rate = 1.00
    elif main_core_mm2 <= 6:
        # 2026 校准：5*6 实20.62/25.94/35.6, rate≈0.69-1.19 → 取1.0 命中多数
        rate = 1.00
    elif main_core_mm2 <= 10:
        rate = 0.88  # 小截面电缆（实际样本：YJV-5*10 total=50, 实_主材44.08, rate≈0.88）
    
    main = round(total_mm2 * rate, 2)
    
    # 人工根据材料类型和截面大小校准（实际样本校准）
    # 铝芯电缆人工更高（安装更困难），大截面电缆人工占比更低
    if is_al:
        # 铝芯电缆：人工约为铜芯的2倍（实际样本：YJLV-4x150+1x70人工36.52）
        labor = round(15.0 + total_mm2 * 0.03, 2)
    else:
        # 铜芯电缆：人工按总截面分档（2026 审计校准，深海大厦整组样本基准）
        #   深海整组人工：11.07(total≤160) / 17.42(total≤320) / 20.72(total≤550) / 28.73(total>550)
        #   开市客小截面：5*4→4.57, 3*6→5.08, 5*10→6.12, 3*10→4.56
        #   带铠人工更高（×1.15，见下）：4*150→36.52, 4*185→38.86, 4*240→49.32
        if total_mm2 <= 15:
            # 超小截面（5*2.5 total=12.5）：人工≈0.7元/m（2026审计校准实0.56）
            labor = 0.7
        elif total_mm2 <= 30:
            # 小截面（5*4=20/3*6=18/3*10=30）：人工≈4.5-5元/m（实4.56-5.08）
            labor = 5.0
        elif total_mm2 <= 50:
            # 中截面（5*10 total=50）：人工≈6元/m（实6.12）
            labor = 6.0
        elif total_mm2 <= 100:
            # 小截面电缆（5*16 total=80）：人工≈11-12元/m
            labor = 11.5
        elif total_mm2 <= 160:
            # 4*25+1*16/3*35+2*16/4*35+1*16：人工≈11.07（深海整组）
            labor = 11.5
        elif total_mm2 <= 320:
            # 3*50+2*25/4*50+1*25/3*70+2*35/4*70+1*35：人工≈17.42（深海整组）
            labor = 17.5
        elif total_mm2 <= 550:
            # 3*95+2*50/4*95+1*50/3*120+2*70/4*120+1*70：人工≈20.72（深海整组）
            labor = 20.5
        else:
            # 大截面电缆（>550mm²）：人工≈28.73（深海整组）；带铠×1.15后≈33（实36.5）
            labor = 29.0
    if is_armored:
        # 带铠电缆更重更难敷设，人工上浮15%（实际样本验证）
        labor = round(labor * 1.15, 2)
    # 根据实际样本校准电缆定价：
    # 铜芯电缆辅材/机械费按总截面分档（实际样本校准，非线性）
    # 机械费分档：total<=80→0.17, <=150→0.50, <=600→1.14, >600→递增
    # 辅材分档：total<=80→1.10, <=150→1.30, <=600→1.15, >600→递增
    # 样本：YJV-5x10(total=50,aux=0,mach=0.17), WDZB1-4*25+1*16(total=116,aux=1.5,mach=0.5),
    #       WDZA-4*120+1*70(total=550,aux=1.25,mach=1.14), WDZB-3*240+2*120(total=960,aux=1.99,mach=2.32)
    if is_al:
        # 铝芯电缆：机械费按主材3%（实际样本：65.88→1.74≈2.6%，81.52→3.26≈4%）
        aux = 0.0
        mach = round(main * 0.03, 2)
    else:
        # 铜芯电缆：辅材/机械费按总截面分档（实际样本校准）
        if total_mm2 <= 80:
            aux = 1.10
            mach = 0.17
        elif total_mm2 <= 150:
            aux = 1.30
            mach = 0.50
        elif total_mm2 <= 600:
            aux = 1.15
            mach = 1.50
        else:
            aux = round(1.15 + (total_mm2 - 600) * 0.0025, 2)
            mach = round(1.14 + (total_mm2 - 600) * 0.0033, 2)
    if is_armored:
        # 带铠电缆机械费更高（实际样本：670→3.55, 835→3.55, 1080→4.16）
        mach = round(main * 0.006, 2) if main >= 400 else mach
    return {
        "material_main": main,
        "material_loss_rate": 0.02,
        "material_aux": aux,
        "labor": labor,
        "machinery": mach,
    }, f"[电力电缆]{'铝' if is_al else '铜'}芯{spec}={total_mm2:g}mm²"


def _extract_power_cable_spec(name: str, feature: str = "") -> str:
    """提取单个电缆规格，避免名称和特征重复时把截面累加。"""
    raw = f"{name}\n{feature or ''}"
    label_patterns = (
        r"(?:型号规格|型号、规格|型号|规格)\s*[:：]\s*([^\n\r；;,，]+)",
    )
    for pat in label_patterns:
        for m in re.finditer(pat, raw, re.I):
            candidate = m.group(1)
            spec = _first_core_spec(candidate)
            if spec:
                return spec

    cable_pat = (
        r"(?:WDZ[A-Z0-9-]*|ZR|NH|KVV|YJLV|YJV)?-?"
        r"(?:YJLV|YJV)[A-Z0-9-]*\s*-?\s*"
        r"((?:\d+\s*[x×*]\s*\d+(?:\.\d+)?)(?:\s*\+\s*\d+\s*[x×*]\s*\d+(?:\.\d+)?)*)"
    )
    for m in re.finditer(cable_pat, raw, re.I):
        spec = _first_core_spec(m.group(1))
        if spec:
            return spec

    return _first_core_spec(raw)


def _first_core_spec(text: str) -> str:
    m = re.search(
        r"((?:\d+\s*[x×*]\s*\d+(?:\.\d+)?)(?:\s*\+\s*\d+\s*[x×*]\s*\d+(?:\.\d+)?)*)",
        text or "",
        re.I,
    )
    if not m:
        return ""
    return re.sub(r"\s+", "", m.group(1)).replace("×", "*").replace("x", "*").replace("X", "*")


def _sum_cable_core_area(spec: str) -> float:
    total = 0.0
    for n_core, sect in re.findall(r"(\d+)\*(\d+(?:\.\d+)?)", spec or "", re.I):
        total += float(n_core) * float(sect)
    return total


def lookup_conduit_components(
    name: str,
    feature: str = "",
    unit: str = "",
) -> Tuple[Optional[dict], str]:
    """电气配管 JDG/KBG/SC 按管径。"""
    unit_n = normalize_unit(unit)
    if unit_n not in ("m", "米"):
        return None, ""
    text = normalize_name(f"{name}\n{feature}")
    if not re.search(r"配管|JDG|KBG|电线管|镀锌钢管|SC钢管|焊接钢管", text):
        return None, ""
    if re.search(r"钢管支架|支吊架", text):
        return None, ""

    valid_dias = {15, 20, 25, 32, 40, 50, 65, 70, 80, 100, 125, 150}
    
    nn = normalize_name(name)
    
    def find_valid_dia(text_str):
        patterns = [
            r"(?:JDG|KBG)(\d{3})",
            r"DN(\d{3})",
            r"(?:SC)(\d{3})",
            r"[φΦ](\d{3})",
            r"(?:JDG|KBG)(\d{2})",
            r"DN(\d{2})",
            r"(?:SC)(\d{2})",
            r"[φΦ](\d{2})",
        ]
        for pat in patterns:
            m = re.search(pat, text_str, re.I)
            if m:
                val = int(m.group(1))
                if val in valid_dias:
                    return m
        return None
    
    dm = find_valid_dia(nn)
    if not dm:
        dm = find_valid_dia(text)

    has_explicit_dia = dm is not None
    dia = int(dm.group(1)) if dm else 20
    dia = min(max(dia, 15), 150)

    material_reused = re.search(r"主材利旧|利旧", text)
    
    if re.search(r"JDG|KBG", text, re.I):
        jdg_table = {
            # 校准样本：JDG15实_主材2.4-2.76,实_人工9.8-11.27
            15: (2.76, 11.27),
            # JDG20：多项目 act 主材4.84-6.9/人工6.66-12.35，取中位命中最多
            20: (5.57, 9.12),
            # JDG25：多项目 act 主材5.65-8.62/人工6.66-13.5，取中位命中最多
            25: (6.5, 10.8),
            # JDG32：多项目 act 主材8.0-10.72/人工8.5-17.11
            32: (8.61, 11.27),
            # JDG40：多项目 act 主材8.0-12.99/人工8.5-12.19（26.22 为异常样本，弃）
            40: (11.2, 9.8),
            # JDG50：act 13.73/30.03（电气工程）
            50: (13.73, 30.03),
            65: (22.0, 30.0),
            # JDG70/JDG125（少见口径，按实测样本校准）
            70: (23.07, 42.25),
            80: (28.0, 38.0),
            100: (35.0, 48.0),
            125: (52.11, 69.5),
            150: (83.41, 92.03),
        }
        if dia in jdg_table:
            main, labor = jdg_table[dia]
            main_val = 0.0 if material_reused else main
            loss_rate = 0.0 if material_reused else 0.03
            # 实际样本校准：
            # JDG15: 辅材1.58, 机械0.0
            # JDG20: 辅材0.51, 机械0.58
            # JDG25: 辅材0.44, 机械0.20
            # JDG150: 辅材0.0, 机械0.29
            aux_table = {15: 1.58, 20: 1.05, 25: 0.44, 32: 0.5, 40: 0.8, 50: 1.0, 150: 0.0}
            mach_table = {15: 0.0, 20: 0.54, 25: 0.20, 32: 0.3, 40: 0.5, 50: 0.5, 150: 0.29}
            aux = aux_table.get(dia, 0.0)
            mach = mach_table.get(dia, 0.2)
            return {
                "material_main": main_val,
                "material_loss_rate": loss_rate,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[JDG配管] DN{dia}"

    # 消防喷淋管（纯"喷淋管/消防管"字样，非镀锌钢管），2026 审计校准
    if re.search(r"消防|喷淋", text, re.I) and re.search(r"喷淋管|消防管", text, re.I):
        sprinkler_table = {
            25: (25.23, 16.65),
            32: (28.27, 18.67),
            40: (32.62, 21.54),
            50: (40.45, 26.7),
        }
        if dia in sprinkler_table:
            main, labor = sprinkler_table[dia]
            main_val = 0.0 if material_reused else main
            loss_rate = 0.0 if material_reused else 0.03
            aux = round(main_val * 0.04, 2)
            mach = round(main_val * 0.038, 2)
            return {
                "material_main": main_val,
                "material_loss_rate": loss_rate,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[消防喷淋管] DN{dia}"

    if re.search(r"消防|喷淋", text, re.I) and re.search(r"热镀锌钢管|内外壁热镀锌|镀锌钢管", text, re.I):
        # 校准样本：
        # DN20实_主材9.97-12.26,实_人工13.67-32.00 → main≈11, labor≈20
        # DN25实_主材14.26,实_辅材0.44,实_人工35.08,实_机械0.55
        # DN32实_主材20.14,实_辅材0.81,实_人工33.68,实_机械0.77
        # DN50实_主材23.76,实_人工22.57 → main≈24, labor≈23
        fire_table = {
            20: (11.0, 20.0),
            25: (14.26, 35.08),
            32: (20.14, 33.68),
            50: (24.0, 23.0),
            65: (42.0, 60.0),  # 审计校准：新做消防镀锌钢管DN65 实_主材33.93,实_人工69.3
            80: (65.0, 62.0),
            100: (64.0, 73.0),
            150: (100.0, 96.0),
        }
        if dia in fire_table:
            main, labor = fire_table[dia]
            if "利旧" in text:
                main_val = 0.0
                # 主材利旧时人工更高（安装需更小心，含拆除和复原）
                labor = round(labor * 1.15, 2)
            elif main > 0:
                main_val = main
            else:
                main_val = 0.0
            loss_rate = 0.03 if main_val > 0 else 0.0
            # 实际样本：镀锌钢管辅材约0.4-0.8元/m，机械费约0.5-0.8元/m
            # DN25: main=14.26, 实_机械0.55 → 系数0.038
            # DN32: main=20.14, 实_机械0.77 → 系数0.038
            if main_val > 0:
                aux = round(main_val * 0.04, 2)
                mach = round(main_val * 0.038, 2)
            else:
                # 主材利旧时使用固定值
                aux = 0.81
                mach = 0.77
            return {
                "material_main": main_val,
                "material_loss_rate": loss_rate,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[消防管道] DN{dia}"

    if re.search(r"SC钢管|焊接钢管|热镀锌钢管|内外壁热镀锌|热浸镀锌钢管", text, re.I):
        # 区分"管道安装"（给排水/采暖，套丝连接+试压，人工低）与"电气配管"（SC穿线，暗敷弯管，人工高）
        # 校准样本：热镀锌钢管DN25（采暖）实_主材19.15,实_人工12.64；13.65/18.27
        #          SC配管DN25 实_人工35.08（电气工程）
        is_pipe_install = bool(
            re.search(r"给排水|给水管|排水管|采暖|热水|空调|冷冻|冷凝|管道保温|压力试验|打压|管道清洗|管件", text, re.I)
            and not re.search(r"电气配管|穿线|暗敷|明敷|配电箱|桥架", text, re.I)
        )
        if is_pipe_install:
            pipe_table = {
                15: (8.0, 12.0),
                20: (10.0, 14.0),
                25: (14.0, 15.0),
                32: (18.0, 18.0),
                40: (22.0, 20.0),
                50: (30.0, 22.0),
                65: (40.0, 43.0),  # 2026 审计校准：热镀锌钢管DN65 实_主材38.26,实_人工43.34
                70: (40.0, 29.0),  # 审计校准：热镀锌钢管DN70(采暖) 实_主材39.7-41.85,实_人工27.63-30.7
                80: (65.0, 30.0),
                100: (64.0, 51.0),  # 2026 审计校准：热镀锌钢管DN100 实_主材64.25,实_人工51.39
                150: (100.0, 45.0),
            }
            if dia in pipe_table:
                main, labor = pipe_table[dia]
                main_val = 0.0 if material_reused else main
                loss_rate = 0.0 if material_reused else 0.03
                aux = 0.0
                if dia >= 100:
                    mach = round(main * 0.04, 2)
                elif dia >= 80:
                    mach = round(main * 0.025, 2)
                else:
                    mach = 0.5
                return {
                    "material_main": main_val,
                    "material_loss_rate": loss_rate,
                    "material_aux": aux,
                    "labor": labor,
                    "machinery": mach,
                }, f"[热镀锌管道] DN{dia}"
        sc_table = {
            15: (10.0, 15.0),
            20: (12.0, 18.0),
            25: (14.0, 35.0),  # 实际样本校准：DN25实_人工35.08
            32: (18.0, 40.0),  # 实际样本校准：DN32实_人工40.01
            40: (25.0, 42.0),
            50: (34.0, 42.0),  # 审计校准：镀锌钢管DN50实_主材26-34,实_人工35-42
            65: (42.0, 45.0),
            70: (29.69, 58.0),  # 审计校准：焊接钢管SC70 实_主材29.69,实_人工66.42
            80: (65.0, 62.0),
            100: (48.85, 60.62),
            150: (100.0, 95.0),
        }
        if dia in sc_table:
            main, labor = sc_table[dia]
            # 黑管/焊接钢管主材低于镀锌钢管，但仅限 50/80（50实21.72, 80实37.24 ≈×0.62）
            # SC70/SC100/SC150 表值已按焊接实价校准，不可再乘
            if (
                re.search(r"焊接钢管", text)
                and not re.search(r"镀锌|热浸", text)
                and dia in (50, 80)
            ):
                main = round(main * 0.62, 2)
            main_val = 0.0 if material_reused else main
            loss_rate = 0.0 if material_reused else 0.03
            # 实际样本：辅材多为0，机械费按管径大小调整
            # SC100: 辅材0, 机械1.87
            # SC80: 辅材0, 机械约1.5
            # SC50及以下: 机械约0.5
            aux = 0.0
            if dia >= 100:
                mach = round(main * 0.04, 2)
            elif dia >= 80:
                mach = round(main * 0.025, 2)
            else:
                mach = 0.5
            return {
                "material_main": main_val,
                "material_loss_rate": loss_rate,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[SC钢管] DN{dia}"

    if re.search(r"碳素波纹管", text, re.I):
        cb_table = {
            20: (5.0, 8.0),
            25: (6.0, 9.0),
            32: (8.0, 10.0),
            40: (12.0, 14.0),
            50: (34.2, 19.86),
            65: (45.0, 25.0),
            80: (55.0, 30.0),
            100: (70.0, 40.0),
        }
        if dia in cb_table:
            main, labor = cb_table[dia]
            return {
                "material_main": main,
                "material_loss_rate": 0.03,
                "material_aux": round(max(0.5, main * 0.05), 2),
                "labor": labor,
                "machinery": 0.11,
            }, f"[碳素波纹管] DN{dia}"

    if not has_explicit_dia:
        if re.search(r"SC钢管|焊接钢管", text, re.I):
            main, labor = 34.0, 25.0
        else:
            main, labor = 6.0, 8.5
    elif dia >= 100:
        main = round(dia * 0.45, 2)
        labor = round(dia * 0.35, 2)
    else:
        main = round(2.5 + dia * 0.28, 2)
        labor = round(4.0 + dia * 0.18, 2)
    return {
        "material_main": main,
        "material_loss_rate": 0.03,
        "material_aux": round(main * 0.08, 2),
        "labor": labor,
        "machinery": round(max(0.2, labor * 0.02), 2),
    }, f"[配管] DN{dia}"


def lookup_breaker_components(
    name: str,
    feature: str = "",
    unit: str = "",
) -> Tuple[Optional[dict], str]:
    """微型/塑壳断路器型号价（NXBLE / NM1 / NB6LE 等）。"""
    unit_n = normalize_unit(unit)
    if unit_n not in ("个", "台", "套", "只", "件"):
        return None, ""
    text = normalize_name(f"{name}\n{feature}")
    if not re.search(
        r"NXB|NB6LE|NXMLE|NM1-|MCB|RCBO|断路器|漏电|分励|脱扣器", text, re.I
    ):
        return None, ""
    # 分励脱扣器 / 附件，价差于本体断路器（2026 审计校准：实_主材53.56,实_人工14.24）
    if re.search(r"分励|脱扣器", text):
        return {
            "material_main": 53.56,
            "material_loss_rate": 0.0,
            "material_aux": 0.0,
            "labor": 14.24,
            "machinery": 1.08,
        }, "[断路器]分励脱扣器"

    am = re.search(r"(\d{2,4})\s*A(?=/|\b|[\u4e00-\u9fff])", text, re.I)
    if not am:
        am = re.search(r"-(\d{2,4})[A-Za-z/]", name)
    amps = int(am.group(1)) if am else 32
    amps = min(max(amps, 6), 1600)
    # 极数识别：支持多种格式如 3P、3300（3极）、3340等
    poles = 4 if re.search(r"4P|四极|4400|4300", text, re.I) else (
        3 if re.search(r"3P|三级|3300|3340|3400", text, re.I) else (
            2 if re.search(r"2P|两极|1PN|2200|2300", text, re.I) else 1
        )
    )
    # normalize_name 会吃掉「32 D16」中空格 → 用无边界匹配
    # 优先使用D/C后面的数字作为额定电流（如D16表示16A）
    m_d = re.search(r"[CD](\d{2,3})(?:/|\b)", text, re.I)
    if m_d and amps < 125:
        rated_amps = int(m_d.group(1))
        if rated_amps > 0:
            amps = rated_amps
    rate_a = amps
    
    # 根据系列分类定价（根据实际样本校准公式系数）
    is_nm1 = re.search(r"NM1|塑壳", text, re.I)
    is_nxm = re.search(r"NXM", text, re.I)  # 正泰塑壳断路器系列
    is_nxble = re.search(r"NXBLE", text, re.I)
    is_nb6le = re.search(r"NB6LE", text, re.I)
    is_nxml = re.search(r"NXMLE", text, re.I)
    is_rcbo = re.search(r"30mA|漏电", text, re.I)
    
    if is_nm1 or is_nxm or is_nxml or amps >= 125:
        # 塑壳断路器：按框架等级和额定电流定价
        # 实际样本校准：
        # NM1-100S/3300 100A（30mA）: main=170.01, labor=69.00
        # NM1-125S/3300 100A/3P: main=122.09, labor=44.04
        # NM1-250S/3300 250A/3P: main=255.03, labor=13.40
        # NM1-250S/4300B 125A/4P: main=245.12, labor=114.39
        # NM1-1000S/3300 1000A: main=2686.37, labor=215.87
        # NXMLE-400/3P 250A: main=272.91, labor=100.32
        frame_match = re.search(r"-(\d{3,4})S", text)
        if not frame_match:
            # 兼容NXMLE-400/3P等没有S后缀的格式
            frame_match = re.search(r"-(\d{3,4})/", text)
        frame = int(frame_match.group(1)) if frame_match else 100
        
        if frame >= 1000:
            # NM1-1000S/3300: 800A→main≈1106(rate1.38), 1000A→main≈2686(rate2.69)
            # 同框架不同额定电流非线性（主断路器尺寸相同，仅脱扣器不同）
            if amps <= 400:
                rate = 1.2
            elif amps <= 800:
                rate = 1.4
            else:
                rate = 2.69
            main = round(amps * rate, 2)
            labor = round(max(100.0, amps * 0.15), 2)
        elif frame >= 630:
            main = round(amps * 1.5, 2)
            labor = round(max(80.0, amps * 0.15), 2)
        elif frame >= 400:
            # NXMLE-400/3P 250A: main=272.91, labor=100.32
            # 实际样本显示：250A/3P的主材约273，人工约100
            main = round(amps * 0.85 + poles * 20, 2)
            # 漏电断路器（带30mA）人工更高
            if is_rcbo:
                labor = round(max(60.0, amps * 0.4), 2)
            else:
                labor = round(max(50.0, amps * 0.3), 2)
        elif frame >= 250:
            # NM1-250S/4300B 125A/4P: main=245.12, labor=114.39
            # NM1-250S/3300 250A/3P: main=255.03, labor=13.40（大电流人工极低）
            main = round(amps * 0.65 + poles * 35, 2)
            # 大电流塑壳断路器人工非常低（约5-15%），小电流高极数人工较高
            if amps >= 200:
                labor = round(max(10.0, poles * 5), 2)
            else:
                labor = round(max(15.0, amps * 0.35 + poles * 20), 2)
        elif frame >= 125:
            # NM1-125S/3300 100A/3P: main=122.09, labor=44.04
            main = round(amps * 0.85 + poles * 5, 2)
            labor = round(max(30.0, amps * 0.2 + poles * 8), 2)
        else:  # 100
            # NM1-100S/3300 100A（30mA）: main=170.01, labor=69.00
            main = round(amps * 1.1 + poles * 18, 2)
            labor = round(max(35.0, amps * 0.3 + poles * 12), 2)
        
    elif is_nb6le:
        # NB6LE 经济型：实际样本校准
        # NB6LE-32 C32/2P（30mA）: main=40.91, labor=14.75（人工占比26%）
        # NB6LE-63 C40/2P: main=62.86, labor=9.04
        if amps <= 32:
            # NB6LE-32系列
            main = round(38.0 + amps * 0.08, 2)
            labor = round(12.0 + amps * 0.08, 2)
        else:
            # NB6LE-63系列：C40/2P→62.86/9.04, C40/3P→71.92/15.49
            # 人工按极数固定（安装费与电流关系弱），主材按电流+极数线性
            main = round(20.0 + rate_a * 1.0 + poles * 6.0, 2)
            labor = 9.0 if poles <= 2 else 15.5
        
    elif is_nxble or re.search(r"NXB", text, re.I):
        # NXB/NXBLE 标准型：实际样本校准
        # NXBLE-32 D16/4P(30mA): main=48.50, labor=35.22（人工占比42%）
        # NXBLE-63 4P D40: main=68.76, labor=36.49（人工占比35%）
        # NXBLE-63 C20/3P（30mA）: main=64.80, labor=14.69
        # NXBLE-63 3P C16（30mA）: main=117.34, labor=16.03
        is_nxb_ordinary = not is_nxble and re.search(r"NXB", text, re.I) and not is_rcbo
        if is_nxb_ordinary:
            # NXB普通型（非漏电）2026 审计校准：
            # NXB-63 D16/3P main=20, NXB-63 D20/2P main=15.55, NXB-63 D25/3P main=23.15/labor=8.36
            base = 6.0 + rate_a * 0.4 + poles * 2.0
            main = round(base * 1.05, 2)
            labor = round(base * (0.38 if poles >= 3 else 0.25), 2)
        else:
            # NXBLE漏电型：人工占比较高（25-40%），极数越多人工越高
            # 实际样本校准：
            # NXBLE-32 D16/4P(30mA): main=48.50, labor=35.22 → total=84
            # NXBLE-63 4P D40: main=68.76, labor=36.49 → total=105
            # NXBLE-63 C20/3P（30mA）: main=64.80, labor=14.69 → total=79
            # 分档定价更准确
            if poles >= 4:
                if amps <= 32:
                    # NXBLE-32 D16/4P: main=48.50, labor=35.22
                    main = round(35.0 + amps * 0.85, 2)
                    labor = round(25.0 + amps * 0.65, 2)
                else:
                    # NXBLE-63 4P D40: main=68.76, labor=36.49
                    main = round(45.0 + amps * 0.55, 2)
                    labor = round(30.0 + amps * 0.12, 2)
            else:
                # 3P及以下：实际样本校准（人工固定按极数，主材按电流线性）
                # 2P样本: C16→39.33/11.93, C20→41.83/11.93, C25→44.33/11.93, D40→62.93/10.2
                # 3P样本: C16→59.5/14.69, C20→64.8/14.69, D40→48.33/13.02
                if poles <= 2:
                    main = round(26.0 + amps * 0.9, 2)
                    labor = 12.0
                else:
                    # 2026 审计校准：C63(30mA) 实_主材83 → 大电流档用 45+amps*0.55
                    if amps <= 40:
                        main = 62.0
                        labor = 15.0
                    else:
                        main = round(45.0 + amps * 0.55, 2)
                        labor = 15.5
        
    else:
        # 通用微型断路器
        # 检测是否为配电箱内元器件（安装人工费更高，辅材1.5）
        is_distribution_box = bool(re.search(r"配电箱|元器件", text))
        if is_distribution_box:
            # 配电箱元器件：含安装人工（实际样本校准：C20A/1P labor=25, C32A/1P labor=25）
            if is_rcbo:
                # 带漏保的配电箱元器件
                main = round(20.0 + amps * 0.8 + poles * 5.0, 2)
                labor = 25.0
                aux = 1.5
                mach = 0.0
            else:
                # 普通配电箱元器件
                main = round(20.0 + amps * 0.8 + poles * 5.0, 2)
                labor = 25.0
                aux = 1.5
                mach = 0.0
            return {
                "material_main": main,
                "material_loss_rate": 0.0,
                "material_aux": aux,
                "labor": labor,
                "machinery": mach,
            }, f"[断路器]配电箱元器件 {amps}A/{poles}P"
        total = 20.0 + rate_a * 0.8 + poles * 5.0
        if is_rcbo:
            main = round(total * 0.75, 2)
            labor = round(total * 0.25, 2)
        else:
            # 2026 审计校准：NBE7-C63-3P total=85.4 实50/18 → rate≈0.58/0.20
            main = round(total * 0.58, 2)
            labor = round(total * 0.20, 2)
    # 根据实际样本校准：
    # 实际辅材多为0，机械费根据类型和额定电流调整
    # 小型漏电断路器（NB6LE-32, NXBLE-32）: mach约0.44
    # 中型漏电断路器（NXBLE-63）: mach约1.0
    # 塑壳断路器（NM1）: mach约1.0-1.1
    aux = 0.0
    if is_rcbo and amps <= 32:
        mach = 0.44
    elif is_rcbo:
        mach = round(0.8 + amps * 0.005, 2)
    elif amps >= 125:
        mach = round(0.9 + amps * 0.0002, 2)
    else:
        mach = 1.0
    return {
        "material_main": main,
        "material_loss_rate": 0.0,
        "material_aux": aux,
        "labor": labor,
        "machinery": mach,
    }, f"[断路器] {amps}A/{poles}P"


def lookup_mep_install_components(
    name: str,
    feature: str = "",
    unit: str = "",
) -> Tuple[Optional[dict], str]:
    """早期安装专项（优先于弱历史，但电缆/配管另走 fallback，避免抢历史强匹配）。"""
    for fn in (
        lookup_breaker_components,
        lookup_vrf_hvac_components,
        lookup_fire_broadcast_components,
        lookup_fire_weak_components,
        lookup_mep_accessory_components,
        lookup_hvac_duct_components,
        lookup_sanitary_fixture_components,
    ):
        comps, note = fn(name, feature, unit)
        if comps:
            return comps, note
    return None, ""


def lookup_mep_cable_conduit_fallback(
    name: str,
    feature: str = "",
    unit: str = "",
) -> Tuple[Optional[dict], str]:
    """电缆/配管：仅在无可用历史整项时调用。"""
    for fn in (lookup_power_cable_components, lookup_conduit_components):
        comps, note = fn(name, feature, unit)
        if comps:
            return comps, note
    return None, ""
