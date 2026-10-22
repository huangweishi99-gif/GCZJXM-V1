# -*- coding: utf-8 -*-
"""精装户型清单定稿口径（吸收 B2-20260706 金标准）。"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from src.knowledge.project_materials import extract_material_codes
from src.normalize.text import normalize_name, normalize_unit


def _pack(
    main: float,
    labor: float,
    aux: float = 0.0,
    mach: float = 0.0,
    loss: float = 0.0,
) -> dict:
    return {
        "material_main": main,
        "material_loss_rate": loss,
        "material_aux": aux,
        "labor": labor,
        "machinery": mach,
    }


# 公区特征：命中后不做户型精装套价
_PUBLIC_AREA_MARKERS = re.compile(
    r"公区|售楼|会所|地库|坡道|大堂|电梯厅|消防栓|弱电井|强电井|"
    r"干挂|背栓|条形空调|装饰风口|肌理无机|轻钢龙骨石膏板吊顶|"
    r"站厅|站台|地铁|候车|出入口|设备区|公共区|转换层"
)
# 户型部位 / 住宅专属
_RESIDENTIAL_MARKERS = re.compile(
    r"卧室|客厅|餐厅|厨房|阳台|玄关|书房|衣帽间|客房|主卧|次卧|卫生间|"
    r"户型|精装|全屋|入户柜|成品衣柜|坐便|洗涤盆|浴霸|油烟机|"
    r"洗碗机|燃气灶|燃气热水器|风管机|房间门|卫生间门|淋浴间|门槛石|挡水条|"
    r"窗台|复合地板|竹、木"
)
# 国标户型清单常见项名（无公区词时按精装口径）
_RESIDENTIAL_LINE_NAMES = re.compile(
    r"块料楼地面|块料墙面|吊顶天棚|天棚抹灰|天棚油漆|天棚装饰板|"
    r"墙面装饰板|墙面乳胶漆|墙面硬包|细石混凝土保护层|砂浆保护层|找坡层"
)


def _is_residential_context(text: str) -> bool:
    if _PUBLIC_AREA_MARKERS.search(text):
        return False
    if _RESIDENTIAL_MARKERS.search(text):
        return True
    return bool(_RESIDENTIAL_LINE_NAMES.search(text))


def lookup_residential_finish_components(
    name: str,
    feature: str = "",
    unit: str = "",
    *,
    city: str = "",
) -> Tuple[Optional[dict], str]:
    unit_n = normalize_unit(unit)
    nn = normalize_name(name)
    text = normalize_name(f"{name}\n{feature}")

    # 带项目物料编号（CT-01/PT-01/ST-02 等）的行，价格由该项目主材表决定，
    # B2 户型死值盖上去会跨项目报错（云湾 CT-01 块料实主材 14 被报 55）。
    # 让位给后续主材编号层与历史匹配。门槛石/挡水条除外：其编号是石材整板价，
    # 放行会被主材表层按板价报（门槛石 ST-02 实 135 报成 830）。
    if extract_material_codes(name, feature) and not re.search(r"门槛石|挡水条|过门石", text):
        return None, ""

    residential = _is_residential_context(text)

    # --- 合入他项：金标准为空，不估數 ---
    if re.search(r"门槛石防水|阳台防水|防水（第一道防水）|防水\(第一道防水\)", nn):
        return _pack(0.0, 0.0), "[精装·合入他项]"

    # 成品卫生间扶手：名称即户型项，特征里的「无障碍/安全抓杆」不能把它挡在住宅语境外，
    # 也不能交给洁具层的配件价（主材15/人工0）。同键两行均为主材135/人工25/辅材2。
    if unit_n in ("套", "个") and re.search(r"卫生间扶手", nn):
        return _pack(135.0, 25.0, 2.0, 0.0), "[精装]卫生间不锈钢扶手"

    # 公区项不套户型精装口径（避免污染海德/深海等）
    if not residential:
        return None, ""

    # 拆除/铲除行不属于住宅精装价型（福永实证：天棚面龙骨及饰面拆除
    # 被 [精装] 口径给 112/m²，应让出给拆除市场参考规则）
    if re.search(r"拆除|铲除", nn):
        return None, ""

    # --- B2 户型定稿编号/型号优先，避免落入粗住宅模板 ---
    if unit_n in ("组", "个", "套") and re.search(r"AB1287-400|箭牌AB1287", text):
        return _pack(778.67, 258.37, 0.0, 1.92), "[精装定稿]坐便器AB1287-400"
    if unit_n in ("m2", "㎡") and re.search(r"块料墙面", nn) and re.search(r"\bN2\b|（防水）N2|防水.*N2", text):
        main = 30.0 if re.search(r"干区", text) else 33.0
        total_aux = 16.9575
        return _pack(main, 40.0, total_aux, 0.0), "[精装定稿]N2防水墙砖"
    if unit_n in ("m2", "㎡") and re.search(r"吊顶天棚D3|天棚D3", text):
        return _pack(45.0, 30.0, 3.0, 0.0), "[精装定稿]D3吊顶天棚"
    if unit_n in ("m2", "㎡") and re.search(r"淋浴间玻璃隔断", text):
        return _pack(385.0, 65.0, 2.0, 0.0), "[精装定稿]淋浴间玻璃隔断"

    # --- 门槛石/挡水石：禁止套公区 ST 表价 ---
    if unit_n in ("m2", "㎡") and re.search(r"门槛石", text) and "找平" not in text:
        # 门槛石作主词且带编号/石材品种（如"门槛石 ST-02""石材门槛石"）：价格由石材决定
        # （云湾5#6# ST-02 实主材850），B2 湿贴死值会压到 135 造成数量级失配 → 放行编号/历史层
        # 注意：名称主体为楼地面/找平层的括号注释行（如"石材楼地面（门槛石ST-02大理石）"）
        # 不在此列，仍走下方湿贴档（其真值即 135/140）
        is_head_stone = bool(
            re.match(r"^(?:石材|大理石|天然石|人造石)?门槛石", nn)
            and (
                re.search(r"ST-?\d{1,2}", nn)
                or re.search(r"大理石|天然石|人造石|米黄|爵士白|雅士白|黑金花|深啡", nn)
            )
        )
        if is_head_stone:
            return None, ""
        # 门槛石厚度18mm价格较高
        if re.search(r"18mm", text):
            return _pack(285.0, 150.0, 25.0, 1.0, 0.03), "[精装]门槛石湿贴18mm"
        return _pack(135.0, 140.0, 12.0, 0.5, 0.03), "[精装]门槛石湿贴"
    if unit_n in ("m", "米") and re.search(r"挡水条", text):
        return _pack(130.0, 35.0, 3.5, 0.5, 0.03), "[精装]卫生间挡水条"

    # --- 保护层/找坡：材料进辅材，不列主材 ---
    if unit_n in ("m2", "㎡") and re.search(r"细石混凝土保护层|C20细石混凝土保护层", text):
        return _pack(0.0, 22.0, 21.0, 2.0 if "卫生间" in text else 0.5), "[精装]50mm细石混凝土保护层"
    if (unit_n in ("m2", "㎡") and re.search(r"砂浆保护层|找坡层|M20水泥砂浆", text)
            and "防水" not in text and "结合层" not in text):
        return _pack(0.0, 22.0, 8.4, 0.5), "[精装]20mm砂浆保护层/找坡"
    if unit_n in ("m3",) and re.search(r"回填|陶粒", text):
        return _pack(385.0, 85.0, 12.0), "[精装]卫生间陶粒回填"

    # --- 块料地面（按面层规格）---
    if unit_n in ("m2", "㎡") and re.search(r"块料楼地面|楼地面", nn):
        # 满贴多工序（30厚结合层+素水泥膏+填缝剂）：辅材含砂浆/胶膏/填缝，非裸铺
        has_bed = bool(re.search(r"结合层|素水泥膏|基层处理剂", text))
        aux = 28.0 if has_bed else 14.0
        if re.search(r"400\s*\*\s*400|防滑瓷砖", text):
            return _pack(45.0, 48.0, aux, 2.0, 0.075), "[精装]地砖400防滑"
        if re.search(r"1500\s*\*\s*750", text):
            return _pack(85.0, 48.0, aux, 2.0), "[精装]地砖1500*750"
        if re.search(r"1200\s*\*\s*600", text):
            return _pack(55.0, 48.0, aux, 2.0), "[精装]地砖1200*600"
        return _pack(55.0, 48.0, aux, 2.0), "[精装]块料楼地面"

    # --- 块料墙面 ---
    if unit_n in ("m2", "㎡") and re.search(r"块料墙面", nn):
        if "岩板" in text:
            return _pack(193.0, 90.0, 16.8, 2.0, 0.05), "[精装]墙面岩板"
        return _pack(55.0, 68.0, 46.8, 2.0, 0.16), "[精装]墙面瓷砖"

    # --- 防水（第二道等单独计价项）---
    if unit_n in ("m2", "㎡") and re.search(r"防水", nn) and re.search(r"JS|防水涂层", text):
        return _pack(26.5, 18.0, 12.0, 0.2), "[精装]JS防水涂层"

    # --- 木地板 ---
    if unit_n in ("m2", "㎡") and re.search(r"复合地板|强化复合|木\(复合\)地板|竹、木", text):
        return _pack(60.0, 20.0, 17.5, 0.5, 0.05), "[精装]强化复合地板"

    # --- 窗台岩板 ---
    if unit_n in ("m2", "㎡") and re.search(r"窗台.*岩板|岩板.*窗台", text):
        return _pack(193.0, 110.0, 16.8, 0.5), "[精装]窗台岩板"

    # --- 吊顶 ---
    if unit_n in ("m2", "㎡") and re.search(r"吊顶天棚|天棚", nn):
        if re.search(r"D7", text):
            return _pack(0.0, 70.0, 49.50, 0.0), "[精装]吊顶天棚D7(主材甲供)"
        if re.search(r"铝扣板", text):
            return _pack(48.0, 45.0, 18.5, 0.5, 0.01), "[精装]铝扣板吊顶"
        if re.search(r"装饰板", nn):
            return _pack(5.5, 57.5, 44.86, 0.5, 0.01), "[精装]天棚装饰板腻子漆"
        # 中山(云湾)「平面吊顶天棚」=纯石膏板平顶(不含乳胶漆)：实主30/人42/辅3；
        # 含乳胶漆/腻子/造型等的吊顶仍走下方「石膏板吊顶+乳胶漆」整包档，避免误压带涂饰的吊顶
        if (
            city == "中山"
            and re.search(r"平面吊顶", nn)
            and re.search(r"石膏板", text)
            and not re.search(r"乳胶漆|涂料|油漆|造型|跌级|弧形", text)
        ):
            return _pack(30.0, 42.0, 3.0, 0.0), "[精装·中山]平面石膏板吊顶(不含乳胶漆)"
        if re.search(r"石膏板|阻燃夹板|乳胶漆", text):
            return _pack(5.5, 94.5, 75.952, 1.5, 0.02), "[精装]石膏板吊顶+乳胶漆"

    if unit_n in ("m2", "㎡") and "天棚装饰板" in nn:
        return _pack(5.5, 57.5, 44.86, 0.5, 0.01), "[精装]天棚装饰板"
    if unit_n in ("m2", "㎡") and re.search(r"天棚抹灰|天棚油漆|平梁、原顶", nn):
        if "防潮" in text or "阳台" in nn:
            return _pack(5.5, 19.5, 5.98, 0.8, 0.02), "[精装]天棚油漆阳台"
        return _pack(5.5, 39.5, 17.86, 0.2, 0.01), "[精装]天棚抹灰原顶"

    if unit_n in ("m", "米") and re.search(r"灯带", nn):
        return _pack(9.9, 38.0, 1.5, 0.2, 0.01), "[精装]灯带槽"

    # --- 金属线条 ---
    if unit_n in ("m", "米") and re.search(r"金属踢脚|铝合金踢脚", text):
        return _pack(13.5, 15.0, 3.5, 0.3, 0.03), "[精装]铝合金踢脚线"
    if unit_n in ("m", "米") and re.search(r"金属装饰线|MT02|黑色铝条", text):
        # 有展开面/展开尺寸/可见宽度或明确不锈钢/古铜材质的线条：放行给金属线条模块
        # 按展开宽度插值（如云湾 MT-01"展开尺寸:…=93mm"、客厅/次卧背景墙不锈钢线条），
        # 避免泛化 28/10 抢价；纯 MT02 黑色铝条仍走本规则。
        if re.search(r"展开面|展开尺寸|不锈钢|古铜", text) or re.search(
            r"宽\s*\d+(?:\.\d+)?\s*mm|\d+(?:\.\d+)?\s*mm\s*宽", text
        ):
            return None, ""
        return _pack(28.0, 10.0, 2.5, 0.2, 0.03), "[精装]金属装饰线"

    # --- 墙面硬装 ---
    if unit_n in ("m2", "㎡") and re.search(r"深色格栅", text):
        return _pack(365.0, 90.0, 50.0, 2.5, 0.03), "[精装]深色格栅面板"
    if unit_n in ("m2", "㎡") and re.search(r"玻璃隔断", nn):
        return _pack(100.0, 85.0, 15.0, 3.0, 0.01), "[精装]钢化玻璃隔断"
    if unit_n in ("m2", "㎡") and re.search(r"墙面硬包|硬包", nn):
        return _pack(230.0, 35.0, 57.5, 2.0, 0.03), "[精装]墙面硬包"
    if unit_n in ("m2", "㎡") and re.search(r"墙面装饰板", nn):
        return _pack(5.5, 54.5, 63.39, 3.07, 0.03), "[精装]墙面装饰板腻子漆"
    if unit_n in ("m2", "㎡") and re.search(r"墙面乳胶漆|乳胶漆", nn) and "天棚" not in nn:
        # PT-01/02/03/04等编号乳胶漆价格较低（含腻子+底漆+面漆）
        if re.search(r"PT-\d+", text):
            return _pack(4.66, 8.15, 1.46, 0.29, 0.02), "[精装]墙面乳胶漆PT系列"
        return _pack(5.5, 19.5, 5.98, 0.8, 0.02), "[精装]墙面乳胶漆"

    # --- 条板隔墙 ---
    if unit_n in ("m2", "㎡") and re.search(r"条板|内隔墙板|轻质内隔墙", text) and "拆除" not in text:
        return _pack(95.0, 45.0, 12.0, 1.5), "[精装]100mm轻质内隔墙条板"

    # --- 成品柜（主材高、安装人工低）---
    if unit_n in ("m2", "㎡") and re.search(r"入户柜", nn):
        return _pack(850.0, 30.0, 35.0, 3.0), "[精装]成品入户柜"
    if unit_n in ("m2", "㎡") and re.search(r"定制成品衣柜|成品衣柜", text):
        return _pack(950.0, 30.0, 35.0, 3.0), "[精装]定制成品衣柜"
    if unit_n in ("m", "米") and re.search(r"厨房吊柜|吊柜", nn):
        return _pack(1150.0, 30.0, 35.0, 3.0), "[精装]厨房吊柜"
    if unit_n in ("m", "米") and re.search(r"厨房地柜|地柜", nn):
        # 中山云湾定稿专项：厨房地柜（m）实_主材950, 实_辅材20, 实_人工180, 实_机械0
        if "中山" in (city or ""):
            return _pack(950.0, 20.0, 180.0, 0.0), "[中山]厨房地柜含台面（定稿）"
        return _pack(1600.0, 30.0, 35.0, 3.0), "[精装]厨房地柜含台面"

    # --- 门 ---
    if unit_n in ("m2", "㎡") and re.search(r"铝合金门|厨房门", text) and "门" in nn:
        return _pack(860.0, 150.0, 35.0, 5.0), "[精装]定制铝合金门(双包㎡)"
    if unit_n in ("樘", "套") and re.search(r"木门|卫生间门|房间门", text):
        if re.search(r"双开门|1600\*|1600\s*x", text):
            return _pack(3360.0, 360.0, 50.0, 5.0), "[精装]定制成品木门(双开)"
        return _pack(770.0, 730.0, 30.0, 2.0), "[精装]定制成品木门(单开)"

    # --- 卫生间小五金/家具 ---
    if unit_n in ("个",) and re.search(r"浴室柜", nn):
        return _pack(1050.0, 150.0, 35.0, 1.5), "[精装]定制浴室柜"
    if unit_n in ("个",) and re.search(r"镜箱", nn):
        # 中山云湾定稿专项：镜箱（套/个）实_主材1600, 实_辅材100, 实_人工380, 实_机械20
        if "中山" in (city or ""):
            return _pack(1600.0, 100.0, 380.0, 20.0), "[中山]定制镜箱（定稿）"
        return _pack(850.0, 95.0, 35.0, 1.5), "[精装]定制镜箱"
    if unit_n in ("套",) and re.search(r"毛巾", text):
        return _pack(268.0, 25.0, 5.0, 1.5), "[精装]毛巾杆/架"

    # --- 洁具（住宅户型，高于会所估算）---
    if unit_n in ("组", "个", "套") and re.search(r"^地漏$|地漏", nn):
        return _pack(55.0, 25.0, 1.5, 0.2), "[精装]不锈钢地漏"
    if unit_n in ("组", "套") and re.search(r"洗脸盆|台盆|洗手盆", text):
        # 卫生间扶手/抓杆名称里常写「部位:洗手盆抓杆」，不能被洗脸盆规则抢走
        if re.search(r"扶手|抓杆", nn):
            return _pack(135.0, 25.0, 2.0, 0.0), "[精装]卫生间不锈钢扶手/抓杆"
        return _pack(320.0, 55.0, 44.0, 0.8), "[精装]洗脸盆含龙头"
    if unit_n in ("组", "套") and re.search(r"洗涤盆|洗菜盆", text):
        # 拖把池（含龙头排水附件）价格较低
        if re.search(r"拖把池", text):
            return _pack(297.18, 57.15, 19.05, 7.62), "[精装]拖把池含龙头"
        # 不锈钢双槽价格较低
        if re.search(r"双槽|不锈钢", text):
            if re.search(r"单槽", text):
                return _pack(176.97, 72.8, 3.77, 0.0), "[精装]不锈钢洗涤盆单槽"
            return _pack(265.0, 83.0, 77.27, 0.0), "[精装]不锈钢洗涤盆双槽"
        return _pack(630.0, 55.0, 44.0, 0.8), "[精装]洗涤盆含龙头"
    if unit_n in ("组", "套", "个") and re.search(r"大便器|坐便器", text):
        return _pack(800.0, 130.0, 15.0, 0.8), "[精装]坐便器"
    if unit_n in ("套", "组") and re.search(r"淋浴器|花洒", text):
        return _pack(1300.0, 85.0, 25.0, 0.8), "[精装]花洒淋浴器"

    # --- 灯具（按特征分部）---
    if unit_n in ("套", "个") and re.search(r"浴霸|三合一", text):
        return _pack(320.0, 40.0, 5.0, 0.2), "[精装]三合一浴霸"
    if unit_n in ("套", "个") and re.search(r"普通灯具|射灯", text):
        return _pack(48.0, 18.0, 1.5, 0.2), "[精装]射灯"
    if unit_n in ("套", "个") and re.search(r"装饰灯|灯具|吸顶|平板灯", text):
        if re.search(r"300\s*\*\s*300|平板灯", text):
            return _pack(42.0, 18.0, 1.5, 0.2), "[精装]嵌入平板灯"
        if re.search(r"吸顶灯", text):
            return _pack(55.0, 18.0, 1.5, 0.2), "[精装]吸顶灯"
        return _pack(55.0, 18.0, 1.5, 0.2), "[精装]装饰灯"

    # --- 家电 ---
    if unit_n in ("台",) and re.search(r"空调|风管机", text):
        # 云湾安装定稿 F 系列风管机：辅材45/人185/机械5.5 恒定，主材按匹数 1515~3381
        # 旧值 1000/1200 系把设备整价误入人工/辅材
        return _pack(3050.0, 185.0, 45.0, 5.5), "[精装]客厅风管机空调（安装口径）"
    if unit_n in ("台",) and re.search(r"燃气热水器|热水器", nn):
        return _pack(3000.0, 180.0, 45.0, 8.5), "[精装]燃气热水器"
    if unit_n in ("台",) and re.search(r"油烟机", nn):
        return _pack(900.0, 250.0, 35.0, 8.5), "[精装]油烟机"
    if unit_n in ("台",) and re.search(r"燃气灶", nn):
        return _pack(1150.0, 85.0, 25.0, 8.5), "[精装]燃气灶"
    if unit_n in ("台",) and re.search(r"洗碗机", nn):
        return _pack(4200.0, 250.0, 35.0, 8.5), "[精装]洗碗机"

    return None, ""
