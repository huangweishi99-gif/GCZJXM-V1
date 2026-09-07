# -*- coding: utf-8 -*-
"""临时：母行成本测算引擎——按工艺类别测算正确人材机成本，输出分析CSV（用后即删）。

返回 (u, w, x, y, note)：主材费/人工/辅材/机械 + 分析说明。u 为不含损耗主材费。
原则：
- 标准化工艺（线条/找平/涂料/铺贴/吊顶/防水等）按市场行情独立测算；
- 定制项目（洗手台/镜柜/吧台/沙盘/风口大件等）以甲方控制价为锚合理拆分；
- 甲供材项（5#6# CT 铺贴）主材费 u=0（由特征"甲供"驱动）；
- 控制价明显低于市场常识的按正确成本填并标注存疑。
"""
import io, sys, os, csv, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def num(name, pattern, default=None):
    m = re.search(pattern, name)
    if m:
        return float(m.group(1))
    return default


def calc(name, unit, ctrl, feat=""):
    n = name
    jg = "甲供" in feat  # 甲供材判定（特征驱动）
    u = w = x = y = None
    note = ""
    # ---------------- 风口（定制，按长度/周长测算） ----------------
    if "风口" in n:
        # 圆形优先（R1550*150 表示圆弧半径）
        m2 = re.search(r"R(\d{3,4})", n)
        if m2:
            r = float(m2.group(1)) / 1000.0
            circ = 3.14159 * 2 * r
            u = round(circ * 55 + 50, 2)
            w, x, y = 45.0, 12.0, 4.0
            note = f"圆形风口周长{circ:.2f}m×55元/m+固定件50测算"
            return u, w, x, y, note
        m = re.search(r"(\d{3,5})\s*[*xX×]\s*(\d{2,3})", n)  # 1570*150
        if m:
            Lmm = float(m.group(1)); hmm = float(m.group(2))
            L = Lmm / 1000.0
            rate = 92 if hmm >= 200 else 68
            u = round(L * rate + 10, 2)
            w, x, y = 22.0, 4.0, 1.0
            note = f"风口按长度{L:.2f}m×{rate}元/m测算"
        else:
            u = round(ctrl * 0.70, 2); w = round(ctrl * 0.15, 2)
            x = round(ctrl * 0.03, 2); y = 2.0
            note = "风口按控制价拆分(未提取规格)"
        return u, w, x, y, note
    # ---------------- 不锈钢线条/踢脚线/卡条（m） ----------------
    if ("不锈钢" in n or "金属" in n or "铝合金" in n) and unit == "m":
        if "围栏" in n:
            u, w, x = 190.0, 55.0, 20.0; note = "不锈钢围栏(栏杆)按成品护栏测算"
        elif "灯槽" in n:
            if "铝合金" in n:
                u, w, x = 70.0, 22.0, 6.0; note = "铝合金型材灯槽测算"
            else:
                u, w, x = 18.0, 8.0, 2.0; note = "不锈钢灯槽(成品槽+安装)测算"
        elif "踢脚线" in n or "脚线" in n:
            mw = re.search(r"展开(?:尺寸|宽度)?[=:：]?[\d+\s]*=\s*(\d{1,3})\s*mm", feat)
            wd = float(mw.group(1)) if mw else 55.0
            if wd >= 70:
                u, w, x = 11.0, 5.0, 0.8
            elif wd >= 50:
                u, w, x = 8.0, 4.5, 0.6
            elif wd >= 40:
                u, w, x = 7.0, 4.5, 0.6
            else:
                u, w, x = 5.5, 4.5, 0.6
            if "圆柱" in n:
                w += 2.0  # 包圆柱异形加工
            if "成品" in n and "铝合金" in n:  # 成品铝脚线
                u, w, x = 5.5, 3.5, 0.4
            note = f"不锈钢踢脚线(展开{wd:g}mm)测算"
        elif "卡条" in n or "型" in n:
            bw = num(n, r"(\d{2,3})\s*mm宽", 5)
            u = round(3.0 + bw * 0.22, 2); w = 4.0; x = 0.5; note = f"不锈钢卡条宽{bw}mm测算"
        else:  # 线条
            mw = re.search(r"展开(?:尺寸|宽度)?[=:：]?[^（(]*?(\d{1,3})\s*mm", feat)
            wd = float(mw.group(1)) if mw else 0.0
            if "半圆" in n:
                wd = 0.0  # 半圆线条按宽度计价
            if wd > 0:
                if wd >= 85:
                    u = round(14.0 + (wd - 85) * 0.1713, 2)  # 85mm以上按1.2mm厚板线性计价(衔接14)
                    w, x = 5.0, 1.0
                elif wd >= 70:
                    u, w, x = 12.0, 4.5, 0.9
                elif wd >= 50:
                    u, w, x = 10.0, 4.5, 0.8
                elif wd >= 30:
                    u, w, x = 7.0, 4.0, 0.7
                else:
                    u, w, x = 5.0, 4.0, 0.6
                note = f"不锈钢线条(展开{wd:g}mm)测算"
            else:
                mw = re.search(r"(\d{2,3})\s*mm", n)
                bw = float(mw.group(1)) if mw else num(n, r"(\d{1,3})\s*mm宽", 5)
                if bw >= 100:
                    u, w, x = 21.0, 6.0, 1.4
                elif bw >= 60:
                    u, w, x = 14.0, 5.0, 1.0
                elif bw >= 50:
                    u, w, x = 13.0, 5.0, 0.9
                elif bw >= 25:
                    u, w, x = 10.0, 5.0, 0.7
                elif bw >= 20:
                    u, w, x = 8.5, 4.5, 0.7
                elif bw >= 15:
                    u, w, x = 7.5, 4.5, 0.6
                elif bw >= 10:
                    u, w, x = 6.5, 4.0, 0.6
                elif bw >= 5:
                    u, w, x = 5.0, 4.0, 0.6
                else:
                    u, w, x = 4.5, 3.5, 0.5
                note = f"不锈钢线条宽{bw}mm测算"
            if wd == 0 and re.search(r"(?<![\d])3mm", n):
                u, w, x = 2.2, 3.0, 0.4
                note = f"不锈钢线条3mm厚窄条测算"
        y = 0.0
        return u, w, x, y, note
    # ---------------- 发光软膜（投影面积，无"吊顶"字样） ----------------
    if "软膜" in n:
        u, w, x, y = 55.0, 28.0, 5.0, 0.0; note = "发光软膜(软膜+灯带+基层)测算"
        return u, w, x, y, note
    # ---------------- 吊顶 / 灯槽 / 基层（m2 或 m） ----------------
    if "铝扣板" in n:
        u, w, x, y = 60.0, 40.0, 4.0, 1.0; note = "铝扣板吊顶(0.6板+三角龙骨)测算"
        return u, w, x, y, note
    if "吊顶" in n:
        if "GRG" in n and "造型" in n and unit == "m2":
            u, w, x, y = 600.0, 250.0, 60.0, 5.0; note = "GRG造型吊顶(定制)测算"
        elif "转换层" in n:
            u, w, x, y = 75.0, 45.0, 8.0, 3.0; note = "天花转换层(角钢+吊杆)测算"
        elif "造型" in n or "投影" in n or "钢骨架" in n:
            if ctrl >= 500:
                u, w, x, y = 320.0, 110.0, 15.0, 4.0; note = "钢骨架造型吊顶(复杂造型角钢+双层基层)测算"
            elif ctrl >= 400:
                u, w, x, y = 260.0, 100.0, 13.0, 4.0; note = "钢骨架造型吊顶(方管+角钢基层)测算"
            else:
                u, w, x, y = 180.0, 95.0, 12.0, 4.0; note = "钢骨架造型吊顶测算"
        elif "铝板" in n:
            u, w, x, y = 110.0, 40.0, 5.0, 1.0; note = "铝板吊顶(1mm铝板+槽钢龙骨)测算"
        elif "软膜" in n:
            u, w, x, y = 55.0, 28.0, 5.0, 0.0; note = "发光软膜吊顶(软膜+灯带)测算"
        elif "跌级" in n:
            u, w, x, y = 45.0, 50.0, 5.0, 1.0; note = "跌级吊顶(轻钢龙骨+双层石膏板+跌级收边)测算"
        else:
            u, w, x, y = 30.0, 42.0, 3.0, 1.0; note = "平面吊顶(轻钢龙骨+双层石膏板)测算"
        return u, w, x, y, note
    if "灯槽" in n:
        if "GRG" in n and unit == "m":
            u, w, x, y = 260.0, 100.0, 35.0, 0.0; note = "GRG装饰板灯槽(定制)测算"
        elif "铝合金型材" in n:
            u, w, x, y = 70.0, 22.0, 6.0, 0.0; note = "铝合金型材灯槽测算"
        elif "圆形" in n:
            u, w, x, y = 55.0, 50.0, 6.0, 0.0; note = "圆形灯槽(木基层+石膏板)测算"
        elif "弧形" in n:
            u, w, x, y = 65.0, 40.0, 5.0, 0.0; note = "弧形灯槽(木基层+石膏板)测算"
        else:
            if "墙面" in n:
                u, w, x = 20.0, 15.0, 2.0
            elif ctrl >= 95:
                u, w, x = 52.0, 32.0, 5.0
            elif ctrl >= 83:
                u, w, x = 46.0, 28.0, 4.0
            elif ctrl >= 65:
                u, w, x = 38.0, 27.0, 3.5
            else:
                m = re.search(r"(\d{2,3})\s*[*+×]", n)
                if m:
                    sz = float(m.group(1))  # 取第一个数（宽）
                else:
                    sz = num(n, r"(\d{2,3})\s*mm", 100)
                if sz >= 300:
                    u, w, x = 35.0, 32.0, 4.0
                elif sz >= 150:
                    u, w, x = 34.0, 28.0, 3.5
                elif sz >= 100:
                    u, w, x = 28.0, 22.0, 3.0
                elif sz >= 50:
                    u, w, x = 26.0, 21.0, 3.0
                else:
                    u, w, x = 20.0, 15.0, 2.0
            u, w, x, y = u, w, x, 0.0
            note = f"灯槽(控制价{ctrl:.0f}元分档测算)"
        return u, w, x, y, note
    if "窗帘盒" in n:
        if "基层" in n:
            u, w, x, y = 38.0, 22.0, 3.0, 0.0; note = "窗帘盒基层(夹板+石膏板)测算"
        elif "双层" in feat or "侧板" in feat:
            u, w, x, y = 50.0, 20.0, 3.0, 0.0; note = "窗帘盒(双层侧板木工板)测算"
        else:
            u, w, x, y = 22.0, 15.0, 2.5, 0.0; note = "窗帘盒(夹板+石膏板)测算"
        return u, w, x, y, note
    if "埃特板" in n:
        u, w, x, y = 35.0, 22.0, 4.0, 0.0; note = "埃特板基层(双层9厚纤维水泥板)测算"
        return u, w, x, y, note
    if "钢骨架" in n and "基层" in n and not ("瓷砖" in n or "石材" in n or "木饰面" in n
            or "木地板" in n or "岩板" in n or "贴砖" in n or "铺贴" in n):
        u, w, x, y = 45.0, 25.0, 5.0, 0.0; note = "钢骨架石膏板基层测算"
        return u, w, x, y, note
    if "方通" in n and "夹板" in n and "隔墙" in n:
        u, w, x, y = 100.0, 35.0, 7.0, 2.0; note = "镀锌方通+12厘阻燃夹板隔墙测算"
        return u, w, x, y, note
    if ("基层板" in n or "天花基层" in n) and "涂料" not in n:
        u, w, x, y = 35.0, 22.0, 3.0, 0.0; note = "天花基层板(夹板+木龙骨)测算"
        return u, w, x, y, note
    if "木龙骨" in n and "石膏板" in n:
        u, w, x, y = 38.0, 18.0, 4.0, 0.0; note = "木龙骨石膏板基层测算"
        return u, w, x, y, note
    if "石膏板基层" in n and "涂料" not in n:
        u, w, x, y = 8.0, 7.0, 1.2, 0.0; note = "石膏板基层测算"
        return u, w, x, y, note
    if "封板" in n:
        u, w, x, y = 28.0, 12.0, 3.0, 0.0; note = "侧面封板测算"
        return u, w, x, y, note
    if "轨道基层" in n:
        u, w, x, y = 85.0, 38.0, 10.0, 0.0; note = "推拉门轨道基层测算"
        return u, w, x, y, note
    # ---------------- 找平 / 垫层 / 防水 / 反坎 ----------------
    if "找平" in n or "自流平" in n:
        if "门槛石" in n:
            th2 = num(n + " " + feat, r"(\d{1,3})\s*(?:mm|厚)", 30)
            if th2 >= 35:
                u, w, x, y = 9.0, 10.0, 1.5, 0.0
            elif th2 >= 30:
                u, w, x, y = 8.0, 9.5, 1.4, 0.0
            else:
                u, w, x, y = 6.0, 9.0, 1.2, 0.0
            note = f"门槛石下砂浆找平{th2:g}mm测算"
        elif "自流平" in n:
            u, w, x, y = 7.0, 6.0, 0.8, 0.0; note = "石膏自流平(5mm)测算"
        else:
            th = num(n + " " + feat, r"(\d{1,3})\s*(?:mm|厚)", 20)
            if "橱柜" in n:
                th = 50
            if th >= 60:
                u, w, x = 16.0, 14.0, 2.2
            elif th >= 50:
                u, w, x = 14.0, 13.0, 2.0
            elif th >= 40:
                u, w, x = 10.0, 11.0, 1.5
            elif th >= 30:
                u, w, x = 8.5, 10.5, 1.3
            elif th >= 20:
                u, w, x = 7.0, 10.0, 1.2
            else:
                u, w, x = 5.0, 8.0, 1.0
            u, w, x, y = u, w, x, 0.0
            note = f"砂浆找平{th:g}mm厚测算"
        return u, w, x, y, note
    if "保护层" in n:
        u, w, x, y = 5.0, 6.0, 0.8, 0.0; note = "水泥砂浆防水保护层测算"
        return u, w, x, y, note
    if ("楼地面" in n or "水泥砂浆" in n or "垫层" in n or "回填" in n) \
            and not ("瓷砖" in n or "块料" in n or "石材" in n or "防滑砖" in n or "贴砖" in n):
        if "回填" in n:
            u, w, x, y = 220.0, 90.0, 25.0, 0.0; note = "陶粒回填(m3)测算"
        elif "轻集料" in n:
            u, w, x, y = 130.0, 60.0, 15.0, 0.0; note = "LC15轻集料混凝土垫层测算"
        elif "地坪漆" in n:
            u, w, x, y = 20.0, 14.0, 2.5, 0.0; note = "水泥砂浆楼地面+地坪漆测算"
        else:
            u, w, x, y = 10.0, 12.0, 1.5, 0.0; note = "水泥砂浆楼地面测算"
        return u, w, x, y, note
    if "防水" in n and "涂料" not in n and "卷材" not in n:
        u, w, x, y = 12.0, 5.0, 0.5, 0.0; note = "聚合物水泥防水涂料(1.5mm)测算"
        return u, w, x, y, note
    if "反坎" in n:
        if "C25" in n:
            u, w, x, y = 12.0, 18.0, 3.0, 0.0; note = "C25混凝土反坎按正确成本测算(控制价3.4元/m明显偏低存疑)"
        elif "C20" in n and "20mm" in n:
            u, w, x, y = 1.5, 3.0, 0.5, 0.0; note = "20mmC20细石混凝土反坎测算"
        elif "C20" in n:
            u, w, x, y = 2.0, 4.0, 0.6, 0.0; note = "C20细石混凝土止反坎测算"
        else:
            u, w, x, y = 12.0, 18.0, 3.0, 0.0; note = "门槛反坎(混凝土+挡水)测算"
        return u, w, x, y, note
    if "抹灰" in n or "抹面" in n:
        u, w, x, y = 8.0, 8.0, 1.0, 0.0; note = "一般抹灰测算"
        return u, w, x, y, note
    if "砌墙" in n or "砌" in n and "砖" in n:
        u, w, x, y = 180.0, 100.0, 25.0, 0.0; note = "轻质砖砌墙(m3)测算"
        return u, w, x, y, note
    # ---------------- 涂料 / 乳胶漆 / 贴膜 / 刷白（先于防水，避免防水无机涂料误配） ----------------
    if "涂料" in n or "乳胶漆" in n or "刷白" in n or "刷漆" in n or "外墙漆" in n:
        if "防水" in n and "涂料" in n and "无机" not in n:
            u, w, x, y = 12.0, 5.0, 0.5, 0.0; note = "聚合物水泥防水涂料(1.5mm)测算"
        elif "艺术涂料" in n:
            if "圆柱" in n:
                u, w, x, y = 80.0, 52.0, 9.0, 0.0
            else:
                u, w, x, y = 60.0, 40.0, 7.0, 0.0
            note = "艺术涂料(含骨架基层)测算"
        elif "刷白" in n and "涂料" not in n:
            u, w, x, y = 3.0, 4.5, 0.5, 0.0; note = "灯箱内部刷白处理测算"
        elif "外墙" in n:
            u, w, x, y = 9.0, 11.0, 1.0, 0.0; note = "外墙漆测算"
        elif "乳胶漆" in n:
            u, w, x, y = 8.0, 10.0, 0.8, 0.0; note = "墙面乳胶漆测算"
        else:
            u, w, x, y = 11.0, 12.0, 1.0, 0.0; note = "无机涂料(一底二面含腻子)测算"
        return u, w, x, y, note
    if "贴膜" in n and "玻璃门" not in n:
        u, w, x, y = 120.0, 48.0, 10.0, 0.0
        note = "仿木纹贴膜(含基层)测算"
        return u, w, x, y, note
    # ---------------- 人造石（门槛石/窗台石/挡水石/下挂板） ----------------
    if ("门槛石" in n or "窗台石" in n or "挡水石" in n or "下挂板" in n or "人造石" in n):
        if "挡水石" in n and unit == "m":
            u, w, x, y = 40.0, 10.0, 3.0, 0.0; note = "人造石挡水石(60*30mm)测算"
            return u, w, x, y, note
        if "下挂板" in n:
            u, w, x, y = 42.0, 14.0, 3.0, 0.0; note = "石材下挂板测算"
            return u, w, x, y, note
        if "天然" in n or "ST-02" in n or ("门槛石" in n and "人造" not in n and "ST-01" not in n):
            u = round(ctrl * 0.65, 2); w = round(ctrl * 0.10, 2)
            x = round(ctrl * 0.03, 2); y = 0.0
            note = "天然石材门槛石按控制价拆分(价格随石种差异大)"
            return u, w, x, y, note
        u, w, x, y = 150.0, 50.0, 12.0, 0.0; note = "人造石(门槛/窗台)测算"
        return u, w, x, y, note
    # ---------------- 石材类（单位优先判定） ----------------
    if "石材" in n or "岩板" in n or ("石" in n and "大理石" in n):
        if unit == "个":
            u, w, x, y = 230.0, 45.0, 15.0, 0.0; note = "干挂石材层板(750*50*50)测算"
            return u, w, x, y, note
        if unit == "块":
            u, w, x, y = 36.0, 9.0, 4.0, 0.0; note = "石材层板(290*190*40小板)测算"
            return u, w, x, y, note
        if unit == "m2" or "干挂" in n:
            if "门牌位" in n and "岩板" in n:
                u, w, x, y = 250.0, 70.0, 20.0, 0.0; note = "门牌位岩板测算"
            elif "干挂" in n and ("弧形" in n or "波形" in n or "半圆" in n):
                u, w, x, y = 1650.0, 200.0, 60.0, 5.0; note = "异形石材干挂(大板特殊加工)测算"
            elif "干挂" in n and ("电视" in n or "背景墙" in n):
                u, w, x, y = 2000.0, 250.0, 80.0, 5.0; note = "背景墙石材干挂(大板异形)测算"
            elif "干挂" in n:
                if "岩板" in n:
                    u, w, x, y = 280.0, 75.0, 20.0, 4.0; note = "岩板干挂测算"
                else:
                    u, w, x, y = 1250.0, 160.0, 50.0, 5.0; note = "天然石材干挂(含钢骨架)测算"
            elif "台阶" in n:
                u, w, x, y = 950.0, 150.0, 50.0, 5.0; note = "石材台阶(钢骨架基层)测算"
            elif "淋浴地面" in n or "楼梯石材" in n:
                u, w, x, y = 165.0, 68.0, 16.0, 0.0; note = "淋浴地面石材铺贴测算"
            elif "楼地面" in n:
                if "凹槽" in n or "排水槽" in n:
                    if ctrl >= 900:
                        u, w, x, y = 800.0, 120.0, 45.0, 4.0; note = "石材楼地面(高端石材凹槽加工)测算"
                    else:
                        u, w, x, y = 500.0, 100.0, 35.0, 4.0; note = "石材楼地面(5x5凹槽加工)测算"
                else:
                    u, w, x, y = 400.0, 95.0, 30.0, 4.0; note = "石材楼地面测算"
            elif "门槛石" in n or "门槛" in n:
                u, w, x, y = 420.0, 75.0, 22.0, 0.0; note = "天然石材门槛石测算"
            elif "窗台石" in n or "窗台" in n:
                u, w, x, y = 160.0, 55.0, 12.0, 0.0; note = "人造窗台石测算"
            elif "置物层板" in n:
                u, w, x, y = 1250.0, 180.0, 55.0, 5.0; note = "石材置物层板测算"
            elif "台面" in n:
                u, w, x, y = 1100.0, 160.0, 50.0, 5.0; note = "石材台面测算"
            elif "包圆柱" in n:
                u, w, x, y = 1300.0, 180.0, 55.0, 5.0; note = "柱阳角石材干挂测算"
            elif "仿木" in n:
                u, w, x, y = 1650.0, 200.0, 60.0, 5.0; note = "仿木纹石材测算"
            elif "墙面" in n:
                if "干挂" in n:
                    u, w, x, y = 1250.0, 160.0, 50.0, 5.0; note = "墙面干挂石材(含钢骨架)测算"
                elif "ST-01" in n:
                    u, w, x, y = 1100.0, 160.0, 55.0, 5.0; note = "墙面贴石材ST-01(高端石材+钢骨架)测算"
                else:
                    u, w, x, y = 700.0, 115.0, 38.0, 4.0; note = "墙面贴石材(钢骨架夹板基层)测算"
            else:
                u, w, x, y = 400.0, 95.0, 30.0, 4.0; note = "石材面层测算"
            return u, w, x, y, note
        elif unit == "m":
            if "扶手" in n:
                u, w, x, y = 60.0, 25.0, 5.0, 0.0; note = "石材扶手测算"
            elif "线条" in n:
                u, w, x, y = 105.0, 28.0, 7.0, 0.0; note = "石材线条测算"
            elif "踢脚线" in n:
                if "弧形" in n:
                    u, w, x, y = 120.0, 25.0, 8.0, 0.0; note = "弧形石材踢脚线测算"
                else:
                    h = num(n + " " + feat, r"(\d{1,3})\s*mm(?:高)?", 50)
                    if h >= 150:
                        u, w, x, y = 85.0, 18.0, 8.0, 0.0; note = f"石材踢脚线(高{h:.0f}mm含石材主材)测算"
                    elif h >= 80:
                        u, w, x, y = 55.0, 14.0, 6.0, 0.0; note = f"石材踢脚线(高{h:.0f}mm含石材主材)测算"
                    else:
                        u, w, x, y = 25.0, 10.0, 4.0, 0.0; note = "石材踢脚线(成品磨边)测算"
            elif "围栏" in n:
                u, w, x, y = 520.0, 120.0, 50.0, 5.0; note = "石材围栏测算"
            else:
                u, w, x, y = 300.0, 80.0, 25.0, 0.0; note = "石材线条(宽)测算"
            return u, w, x, y, note
    # ---------------- 木饰面 / 木地板（顺序：柜/门头板/暗门/防火门/隔断/门/门套…） ----------------
    if "木饰面" in n or "木塑" in n or "实木线条" in n or "烤漆板" in n or "座椅" in n or "木地板" in n:
        if "柜" in n or "柜体" in n:
            u = round(ctrl * 0.55, 2); w = round(ctrl * 0.17, 2)
            x = round(ctrl * 0.06, 2); y = round(ctrl * 0.01, 2)
            note = "木饰面定制柜按控制价拆分(主材55%/人工17%/辅材6%/机械1%)"
            return u, w, x, y, note
        if "门头板" in n:
            u, w, x, y = 270.0, 55.0, 16.0, 0.0; note = "木饰面门头板测算"
            return u, w, x, y, note
        if "暗门" in n:
            u = round(ctrl * 0.60, 2); w = round(ctrl * 0.18, 2)
            x = round(ctrl * 0.06, 2); y = 0.0
            note = "木饰面暗门(骨架+面层)按控制价拆分"
            return u, w, x, y, note
        if "防火门" in n:
            u, w, x, y = 260.0, 55.0, 16.0, 0.0; note = "防火门包木饰面测算"
            return u, w, x, y, note
        if "隔断" in n and "门" in n:
            u, w, x, y = 520.0, 115.0, 42.0, 0.0; note = "木饰面隔断门及隔断测算"
            return u, w, x, y, note
        if "烤漆板" in n and "墙面" in n and "线条" not in n:
            u, w, x, y = 350.0, 70.0, 22.0, 0.0; note = "烤漆板饰面(锣槽造型)测算"
            return u, w, x, y, note
        if "门" in n:
            if "樘" == unit:
                u, w, x, y = 1050.0, 170.0, 55.0, 0.0; note = "木饰面门(含门扇+门套+五金)测算"
            elif "门套" in n and "不含门套" not in n:
                if "造型" in n or "投影" in n:
                    u, w, x, y = 350.0, 75.0, 22.0, 0.0; note = "造型木饰面门套(投影面积)测算"
                else:
                    u, w, x, y = 250.0, 60.0, 16.0, 0.0; note = "木饰面门套测算"
            else:
                u, w, x, y = 1250.0, 180.0, 60.0, 0.0; note = "木饰面门(m2计价)测算"
            return u, w, x, y, note
        if "踢脚线" in n or "脚线" in n:
            u, w, x, y = 46.0, 12.0, 3.0, 0.0; note = "木饰面踢脚线测算"
            if "木塑" in n:
                u, w, x, y = 7.0, 3.0, 0.5, 0.0
            return u, w, x, y, note
        if "线条" in n:
            if "烤漆板" in n:
                if "50" in n and "80" in n:
                    u, w, x, y = 45.0, 10.0, 2.0, 0.0
                elif "圆弧" in n or "弧形" in n:
                    u, w, x, y = 8.0, 4.0, 0.6, 0.0
                else:
                    u, w, x, y = 6.0, 3.0, 0.5, 0.0
            else:
                u, w, x, y = 6.0, 3.0, 0.5, 0.0
            note = "定制木线条测算"
            return u, w, x, y, note
        if "木地板" in n:
            if "WD-01" in n:
                u, w, x, y = 75.0, 17.0, 3.0, 0.0; note = "实木复合木地板(12mm)测算"
            else:
                u, w, x, y = 165.0, 20.0, 4.0, 0.0; note = "18mm木地板测算"
            if "钢骨架" in n or "地台" in n:
                u += 45.0; w += 25.0; x += 5.0
                note += "+钢骨架夹板基层"
            return u, w, x, y, note
        if "座椅" in n:
            u, w, x, y = 270.0, 55.0, 16.0, 0.0; note = "木饰面座椅测算"
            return u, w, x, y, note
        if "弧形" in n or "圆柱" in n:
            u, w, x, y = 330.0, 70.0, 20.0, 0.0; note = "弧形木饰面测算"
            return u, w, x, y, note
        if "隔墙" in n or "包管" in n:
            u, w, x, y = 225.0, 50.0, 15.0, 0.0; note = "木饰面(隔墙/包管)测算"
            return u, w, x, y, note
        if "密拼" in n:
            u, w, x, y = 260.0, 55.0, 16.0, 0.0; note = "木饰面密拼测算"
            return u, w, x, y, note
        if "钢骨架" in n:
            u, w, x, y = 330.0, 75.0, 22.0, 0.0; note = "木饰面(钢骨架基层)测算"
            return u, w, x, y, note
        u, w, x, y = 250.0, 55.0, 16.0, 0.0; note = "木饰面WD-01测算"
        return u, w, x, y, note
    # ---------------- 门头梁 / 电动移门（先于门套，避免误配） ----------------
    if "门头梁" in n:
        u, w, x, y = 120.0, 30.0, 10.0, 0.0; note = "热镀锌角钢门头梁测算"
        return u, w, x, y, note
    if "电动" in n and "移门" in n:
        u, w, x, y = 21000.0, 3500.0, 1500.0, 200.0; note = "电动移门(6m宽感应系统+玻璃+轨道)测算"
        return u, w, x, y, note
    # ---------------- 门套 / 门（不锈钢/玻璃） ----------------
    if "石脚座" in n:
        u, w, x, y = 15.0, 5.0, 1.5, 0.0; note = "门套石脚座(人造石)测算"
        return u, w, x, y, note
    if ("门套" in n and "不含门套" not in n and "石脚座" not in n) \
            or ("门头" in n and "门头梁" not in n) or "窗套" in n:
        if "蚀刻" in n:
            u, w, x, y = 500.0, 100.0, 30.0, 0.0; note = "蚀刻不锈钢门头测算"
        elif "造型" in n or "透光" in n:
            u, w, x, y = 215.0, 60.0, 18.0, 0.0; note = "不锈钢门头(造型/透光)测算"
        else:
            if ctrl >= 400:
                u, w, x, y = 300.0, 75.0, 22.0, 0.0; note = "不锈钢门套(大堂高配1.2mm+钢架基层)测算"
            else:
                u, w, x, y = 200.0, 68.0, 19.0, 0.0; note = "不锈钢门套(1.2mm+基层)测算"
        return u, w, x, y, note
    if "钢化玻璃门" in n or "玻璃门" in n:
        if "磨砂" in n or "贴膜" in n:
            u, w, x, y = 780.0, 140.0, 50.0, 0.0; note = "超白钢化玻璃门(磨砂贴膜含五金)测算"
        else:
            u, w, x, y = 720.0, 130.0, 45.0, 0.0; note = "超白钢化玻璃门(含五金)测算"
        return u, w, x, y, note
    if "推拉门" in n or ("移门" in n and "电动" not in n):
        if "淋浴屏" in n:
            u, w, x, y = 380.0, 90.0, 30.0, 4.0; note = "淋浴屏(钢化玻璃+五金)测算"
        elif "夹丝" in n or "夹金属丝" in n or "夹金属丝" in feat:
            if "四联动" in feat or "四联动" in n:
                u, w, x, y = 620.0, 140.0, 85.0, 5.0; note = "夹丝玻璃推拉门(四联动重型轨道)测算"
            elif "厨房" in n or "多功能" in n or "卫生间" in n or "衣帽间" in n:
                u, w, x, y = 320.0, 65.0, 40.0, 5.0; note = "夹丝玻璃移门(12mm夹丝+不锈钢边框+轨道)测算"
            else:
                u, w, x, y = 620.0, 140.0, 85.0, 5.0; note = "夹丝玻璃推拉门(12mm夹丝+不锈钢边框+重型轨道)测算"
        else:
            if "厨房" in n or "多功能" in n or "卫生间" in n or "衣帽间" in n:
                u, w, x, y = 280.0, 60.0, 35.0, 5.0; note = "玻璃移门(不锈钢边框+轨道)测算"
            else:
                u, w, x, y = 750.0, 140.0, 50.0, 5.0; note = "玻璃推拉门(玻璃+型材+轨道五金)测算"
        return u, w, x, y, note
    if "夹金属丝玻璃" in n and "门" in n:
        u, w, x, y = 800.0, 150.0, 55.0, 5.0; note = "夹丝玻璃门(含五金)测算"
        return u, w, x, y, note
    if "玻璃" in n and ("隔断" in n or "推拉窗" in n):
        if "夹丝" in n or "夹金属丝" in n:
            u, w, x, y = 700.0, 120.0, 50.0, 5.0; note = "夹丝玻璃隔断测算"
        else:
            u, w, x, y = 650.0, 120.0, 45.0, 0.0; note = "玻璃门/窗测算"
        return u, w, x, y, note
    if "银镜" in n and "不锈钢" not in n:
        u, w, x, y = 110.0, 35.0, 8.0, 0.0; note = "银镜(5mm含基层)测算"
        return u, w, x, y, note
    if "镜子饰面" in n or "镜面饰面" in n:
        u, w, x, y = 200.0, 45.0, 15.0, 0.0; note = "镜子饰面(镜面+基层+收边)测算"
        return u, w, x, y, note
    if "透光" in n:
        u, w, x, y = 190.0, 50.0, 15.0, 0.0; note = "透光亚克力/透光板测算"
        return u, w, x, y, note
    if "屏风" in n:
        if "沙盘" in n or "前厅" in n or "通道" in n:
            u, w, x, y = 780.0, 180.0, 70.0, 5.0; note = "高配屏风测算"
        else:
            u, w, x, y = 520.0, 150.0, 60.0, 5.0; note = "屏风(金属框架+饰面)测算"
        return u, w, x, y, note
    # ---------------- 硬包 / 墙布 / 扪皮 ----------------
    if "扪皮" in n:
        u, w, x, y = 140.0, 40.0, 12.0, 0.0; note = "扪皮饰面(皮革+板基层)测算"
        return u, w, x, y, note
    if "硬包" in n or "扪布" in n:
        u, w, x, y = 150.0, 42.0, 11.0, 0.0; note = "硬包(皮革+板)测算"
        return u, w, x, y, note
    if ("墙布" in n or "皮革" in n) and "不锈钢" not in n:
        if "背景" in n or "床背" in n or "床靠" in n or "皮雕" in n:
            u, w, x, y = 165.0, 48.0, 16.0, 0.0; note = "背景墙高档墙布/皮雕测算"
        else:
            u, w, x, y = 95.0, 35.0, 10.0, 0.0; note = "墙布测算"
        return u, w, x, y, note
    # ---------------- 美缝（先于瓷砖，避免"瓷砖美缝"误入铺贴） ----------------
    if "美缝" in n:
        u, w, x, y = 8.0, 6.5, 0.5, 0.0; note = "瓷砖美缝测算"
        return u, w, x, y, note
    # ---------------- 瓷砖铺贴（甲供由特征驱动） ----------------
    if ("瓷砖" in n or "块料" in n or "防滑砖" in n or "贴砖" in n) \
            and ("铺贴" in n or "地面" in n or "墙面" in n or "踢脚线" in n or "块料" in n
                 or "拼花" in n or "干挂" in n or "挂贴" in n or "包管" in n or "包墩" in n
                 or "钢骨架" in n):
        if "拼花" in n:
            u, w, x, y = 110.0, 70.0, 18.0, 0.0; note = "瓷砖拼花铺贴测算"
            return u, w, x, y, note
        if "踢脚线" in n:
            if unit == "m2":
                u, w, x, y = 60.0, 55.0, 15.0, 0.0; note = "瓷砖踢脚线(m2计价)测算"
            elif "CT-01" in n:
                u, w, x, y = 110.0, 25.0, 8.0, 0.0; note = "瓷砖踢脚线(CT-01高端)测算"
            elif jg:
                u, w, x, y = 0.0, 5.5, 1.5, 0.0; note = "瓷砖踢脚线(甲供)测算"
            else:
                u, w, x, y = 6.0, 5.5, 1.5, 0.0; note = "瓷砖踢脚线(含砖)测算"
            return u, w, x, y, note
        if "干挂" in n:
            if "蜂窝板" in feat or "铝蜂窝" in feat:
                u, w, x, y = 320.0, 110.0, 35.0, 5.0; note = "瓷砖干挂(铝蜂窝复合板+钢骨架)测算"
            else:
                u, w, x, y = 180.0, 95.0, 25.0, 4.0; note = "瓷砖干挂(钢骨架+挂件)测算"
            return u, w, x, y, note
        if "挂贴" in n:
            u, w, x, y = 35.0, 48.0, 20.0, 2.0; note = "瓷砖挂贴(含找平挂件)测算"
            return u, w, x, y, note
        if "包管" in n or "包墩" in n:
            u, w, x, y = 35.0, 55.0, 15.0, 0.0; note = "包管贴砖(含砌筑)测算"
            return u, w, x, y, note
        if "钢骨架" in n:
            u, w, x, y = 150.0, 80.0, 25.0, 4.0; note = "贴砖(钢骨架夹板基层)测算"
            return u, w, x, y, note
        if "墙面" in n:
            if jg:
                u, w, x, y = 0.0, 38.0, 13.5, 1.5; note = "墙面瓷砖铺贴(甲供砖)测算"
            elif "CT-01" in n and ctrl >= 300:
                u, w, x, y = 260.0, 75.0, 22.0, 3.0; note = "墙面瓷砖CT-01大板薄贴(含砖背胶美缝)测算"
            else:
                u, w, x, y = 90.0, 38.0, 13.5, 1.5; note = "墙面瓷砖铺贴(含砖)测算"
        elif unit == "m2":
            if jg or (("CT-03" in n or "CT-04" in n) and ctrl < 60):
                if "CT-03" in n:
                    u, w, x, y = 0.0, 27.0, 13.5, 1.5; note = "地面瓷砖铺贴(甲供砖CT-03小砖)测算"
                else:
                    u, w, x, y = 0.0, 29.0, 13.5, 1.5; note = "地面瓷砖铺贴(甲供砖)测算"
            else:
                u, w, x, y = 70.0, 32.0, 14.0, 1.5; note = "地面瓷砖铺贴(含砖+找平)测算"
        else:
            u, w, x, y = 0.0, 5.5, 1.5, 0.0; note = "瓷砖铺贴(零星)测算"
        return u, w, x, y, note
    # ---------------- 定制家具 / 柜类（控制价锚定拆分） ----------------
    if ("洗手台" in n or "镜柜" in n or "镜箱" in n or "吧台" in n or "沙盘" in n
            or "接待台" in n or "低柜" in n or "吊架" in n or "电梯按钮" in n
            or "衣柜" in n or "书柜" in n or "装饰柜" in n or "玄关柜" in n
            or "橱柜" in n or "冰箱柜" in n or "阳台柜" in n or "岛台" in n
            or "书桌" in n or "梳妆台" in n or "水吧柜" in n or "水吧台" in n
            or "吊柜" in n or "高柜" in n or "暗门" in n or "矮柜" in n
            or "置物柜" in n or "储物柜" in n or "收纳柜" in n or "壁柜" in n
            or "柜子" in n or "柜体" in n):
        if "吊架" in n:
            u, w, x, y = 560.0, 130.0, 44.0, 0.0; note = "不锈钢装饰吊架测算"
        elif "电梯按钮" in n and unit != "m2":
            u, w, x, y = 105.0, 22.0, 6.0, 0.0; note = "电梯按钮面板测算"
        elif "暗门" in n:
            u = round(ctrl * 0.60, 2); w = round(ctrl * 0.18, 2)
            x = round(ctrl * 0.06, 2); y = 0.0
            note = "暗门(骨架+面层)按控制价拆分"
        else:
            u = round(ctrl * 0.55, 2); w = round(ctrl * 0.17, 2)
            x = round(ctrl * 0.06, 2); y = round(ctrl * 0.01, 2)
            note = "定制柜/家具按控制价拆分(主材55%/人工17%/辅材6%/机械1%)"
        return u, w, x, y, note
    # ---------------- 角钢 / 结构 ----------------
    if "角钢" in n:
        if "t" == unit:
            u, w, x, y = 5600.0, 1600.0, 540.0, 100.0; note = "镀锌角钢(t)测算"
        else:
            u, w, x, y = 120.0, 30.0, 10.0, 0.0; note = "镀锌角钢门头梁测算"
        return u, w, x, y, note
    # ---------------- GRG 线条 / 石膏线条 / 角线 ----------------
    if "GRG" in n and "线条" in n:
        u, w, x, y = 46.0, 6.0, 3.0, 1.0; note = "GRG线条(65*55定制)测算"
        return u, w, x, y, note
    if "石膏线条" in n or "石膏角线" in n:
        if "弧" in n:
            u, w, x, y = 6.0, 4.0, 0.6, 0.0; note = "石膏角线(弧形)测算"
            return u, w, x, y, note
        sz = num(n, r"(\d{2,3})\s*[*×]?\s*(\d{2,3})", 30) if re.search(r"\d{2,3}\s*[*×]", n) else num(n, r"(\d{2,3})\s*mm", 30)
        if sz and sz >= 100:
            u, w, x, y = 9.0, 4.5, 0.8, 0.0; note = "定制耐水石膏线条(大)测算"
        elif sz and sz >= 60:
            u, w, x, y = 5.0, 3.5, 0.5, 0.0; note = "定制耐水石膏线条(中)测算"
        else:
            u, w, x, y = 4.0, 3.0, 0.4, 0.0; note = "成品石膏角线测算"
        return u, w, x, y, note
    # ---------------- 其他 ----------------
    if "地胶" in n:
        u, w, x, y = 90.0, 32.0, 8.0, 0.0; note = "PVC地胶(含自流平垫层)测算"
        return u, w, x, y, note
    if "胶地板" in n:
        if "基层" in n:
            u, w, x, y = 22.0, 10.0, 2.0, 0.0; note = "胶地板基层(30mm找平+自流平)测算"
        else:
            u, w, x, y = 45.0, 12.0, 3.0, 0.0; note = "定制胶地板(PVC成品+胶粘)测算"
        return u, w, x, y, note
    if "树脂板" in n:
        u, w, x, y = 220.0, 52.0, 16.0, 0.0; note = "树脂板饰面测算"
        return u, w, x, y, note
    if "LOGO" in n:
        u, w, x, y = 100.0, 30.0, 8.0, 0.0; note = "蚀刻LOGO测算"
        return u, w, x, y, note
    if "门牌位" in n:
        if "岩板" in n:
            u, w, x, y = 250.0, 70.0, 20.0, 0.0; note = "门牌位岩板测算"
        elif "WD-01" in n or "木饰面" in n:
            u, w, x, y = 110.0, 30.0, 8.0, 0.0; note = "门牌位木饰面测算"
        else:
            u, w, x, y = 155.0, 52.0, 14.0, 0.0; note = "门牌位不锈钢饰面测算"
        return u, w, x, y, note
    if "不锈钢" in n and "饰面" in n:
        if "镜面" in n:
            u, w, x, y = 120.0, 38.0, 12.0, 0.0; note = "镜面不锈钢饰面测算"
        else:
            u, w, x, y = 155.0, 52.0, 14.0, 0.0; note = "不锈钢饰面测算"
        return u, w, x, y, note
    if ("不锈钢" in n or "镜面不锈钢" in n) and ("MT-01" in n or "MT-02" in n or "MT-03" in n
            or "内嵌盒" in n or "壁龛" in n or "面层" in n or "发光字" in n or "壁灯位" in n):
        if "天花" in n and "MT-03" in n:
            u, w, x, y = 280.0, 55.0, 18.0, 0.0; note = "天花镜面不锈钢(含基层造型)测算"
        elif "MT-01" in n:
            u, w, x, y = 200.0, 48.0, 16.0, 0.0; note = "墙面镜面不锈钢饰面(含基层收边)测算"
        elif "MT-02" in n:
            u, w, x, y = 165.0, 42.0, 14.0, 0.0; note = "镜面不锈钢饰面(含基层收边)测算"
        elif "天花" in n:
            u, w, x, y = 280.0, 55.0, 18.0, 0.0; note = "天花镜面不锈钢(含基层造型)测算"
        else:
            u, w, x, y = 200.0, 48.0, 16.0, 0.0; note = "镜面不锈钢饰面(含基层收边)测算"
        return u, w, x, y, note
    if "石材层板" in n and unit == "块":
        u, w, x, y = 36.0, 9.0, 4.0, 0.0; note = "石材层板(290*190*40小板)测算"
        return u, w, x, y, note
    if "地坪漆" in n:
        u, w, x, y = 18.0, 9.0, 1.8, 0.0; note = "地坪漆测算"
        return u, w, x, y, note
    if "金属膜" in n:
        u, w, x, y = 38.0, 10.0, 2.0, 0.0; note = "金属贴膜测算"
        return u, w, x, y, note
    if "导轨盒" in n:
        u, w, x, y = 80.0, 18.0, 6.0, 0.0; note = "导轨盒(厨房门)测算"
        return u, w, x, y, note
    if "铜条" in n:
        u, w, x, y = 20.0, 5.0, 1.0, 0.0; note = "成品铜条(3mm)测算"
        return u, w, x, y, note
    if "包管" in n or "包墩" in n:
        u, w, x, y = 38.0, 15.0, 3.0, 0.0; note = "方通+阻燃夹板包管测算"
        return u, w, x, y, note
    if "波纹板" in n:
        u, w, x, y = 305.0, 35.0, 10.0, 5.0; note = "波纹板饰面(9mm阻燃夹板基层)测算"
        return u, w, x, y, note
    if "波浪板" in n:
        u, w, x, y = 520.0, 120.0, 40.0, 5.0; note = "波浪板挂贴测算"
        return u, w, x, y, note
    if "收边条" in n:
        u, w, x, y = 6.0, 2.5, 0.4, 0.0; note = "L型收边条测算"
        return u, w, x, y, note
    if "装饰线条" in n:
        u, w, x, y = 25.0, 6.0, 1.5, 0.0; note = "成品装饰线条测算"
        return u, w, x, y, note
    if "隔断" in n:
        u, w, x, y = 350.0, 80.0, 25.0, 0.0; note = "小便隔断测算"
        return u, w, x, y, note
    if "淋浴屏" in n:
        u, w, x, y = 380.0, 90.0, 30.0, 4.0; note = "淋浴屏(钢化玻璃+五金)测算"
        return u, w, x, y, note
    # ---------------- 机电安装（消防电/消防水，市场价测算） ----------------
    if "剔槽" in n:
        u, w, x, y = 0.0, 20.0, 2.0, 2.5; note = "剔槽(70*70线管)测算"
        return u, w, x, y, note
    if "消防模块箱" in n:
        u, w, x, y = 100.0, 30.0, 8.0, 0.0; note = "消防模块箱(箱体+端子)测算"
        return u, w, x, y, note
    if "总线短路隔离器" in n:
        u, w, x, y = 230.0, 15.0, 5.0, 0.0; note = "总线短路隔离器(设备含安装)测算"
        return u, w, x, y, note
    if "消防模块" in n:
        u, w, x, y = 110.0, 25.0, 8.0, 0.0; note = "消防模块(输入输出模块)测算"
        return u, w, x, y, note
    if "点型探测器" in n:
        u, w, x, y = 40.0, 15.0, 4.0, 0.0; note = "点型感烟/感温探测器测算"
        return u, w, x, y, note
    if "电话插孔" in n:
        u, w, x, y = 15.0, 5.0, 1.5, 0.0; note = "消防报警电话插孔测算"
        return u, w, x, y, note
    if "声光报警器" in n:
        u, w, x, y = 80.0, 18.0, 6.0, 0.0; note = "声光报警器测算"
        return u, w, x, y, note
    if "消防电话分机" in n:
        u, w, x, y = 35.0, 10.0, 3.0, 0.0; note = "消防电话分机测算"
        return u, w, x, y, note
    if "吸顶式扬声器" in n:
        u, w, x, y = 25.0, 8.0, 3.0, 0.0; note = "吸顶式扬声器测算"
        return u, w, x, y, note
    if "配管" in n:
        u, w, x, y = 7.0, 3.5, 0.8, 0.0; note = "电气配管(JDG管)测算"
        return u, w, x, y, note
    if "管内穿线" in n:
        u, w, x, y = 2.5, 2.0, 0.3, 0.0; note = "管内穿线(BV线)测算"
        return u, w, x, y, note
    if "钢质接线盒" in n:
        u, w, x, y = 6.0, 2.5, 0.5, 0.0; note = "钢质接线盒(86型)测算"
        return u, w, x, y, note
    if "按钮" in n:
        u, w, x, y = 60.0, 15.0, 5.0, 0.0; note = "手动/消火栓报警按钮测算"
        return u, w, x, y, note
    if "热浸镀锌钢管" in n:
        if ctrl >= 120:
            u, w, x, y = 100.0, 18.0, 8.0, 0.0; note = "热镀锌钢管DN150按市场价测算"
        elif ctrl >= 85:
            u, w, x, y = 72.0, 14.0, 6.0, 0.0; note = "热镀锌钢管DN100按市场价测算"
        elif ctrl >= 70:
            u, w, x, y = 56.0, 12.0, 5.0, 0.0; note = "热镀锌钢管DN80按市场价测算"
        elif ctrl >= 55:
            u, w, x, y = 46.0, 10.0, 4.5, 0.0; note = "热镀锌钢管DN65按市场价测算"
        elif ctrl >= 40:
            u, w, x, y = 38.0, 9.0, 4.0, 0.0; note = "热镀锌钢管DN50按市场价测算"
        else:
            u, w, x, y = 25.0, 8.0, 3.0, 0.0; note = "热镀锌钢管DN32按市场价测算"
        return u, w, x, y, note
    if "管道支架" in n:
        u, w, x, y = 18.0, 5.0, 2.0, 0.0; note = "管道支架(镀锌型钢制安+防腐)测算"
        return u, w, x, y, note
    if "铜截止阀" in n:
        u, w, x, y = 55.0, 8.0, 3.0, 0.0; note = "铜截止阀(DN25)测算"
        return u, w, x, y, note
    if "截止阀" in n:
        u, w, x, y = 110.0, 15.0, 6.0, 0.0; note = "截止阀(大口径)测算"
        return u, w, x, y, note
    if "喷头" in n:
        u, w, x, y = 18.0, 6.0, 2.0, 0.0; note = "直立式洒水喷头测算"
        return u, w, x, y, note
    # ---------------- 架空层成品家具 / 健身器材 / 墙绘（成品采购，控制价拆分） ----------------
    if "架空层" in n or "墙绘" in n or "户外沙发" in n:
        if "墙绘" in n:
            u = round(ctrl * 0.60, 2); w = round(ctrl * 0.20, 2)
            x = round(ctrl * 0.05, 2); y = 0.0
            note = "艺术墙绘(手绘+材料)按控制价拆分"
        else:
            u = round(ctrl * 0.70, 2); w = round(ctrl * 0.12, 2)
            x = round(ctrl * 0.04, 2); y = round(ctrl * 0.01, 2)
            note = "架空层成品家具/健身器材按控制价拆分(成品采购无独立测算基础)"
        return u, w, x, y, note
    return None


# ---- 遍历母行测算（全量：所有有成本/控制价的母行） ----
rows = list(csv.DictReader(open(r"data\tmp\母行差异分析.csv", encoding="utf-8-sig")))
bad = [r for r in rows if r["类型"] == "母行" and r["差异%"] not in (None, "")]
no_diff = [r for r in rows if r["类型"] == "母行" and r["差异%"] in (None, "")]
print(f"母行总数: {len(bad)}  无差异(成本或控制价为0): {len(no_diff)}")

out = []
unmatched = []
for r in bad:
    name = r["项目名称"]
    unit = r["单位"]
    ctrl = float(r["控制价"]) if r["控制价"] else 0.0
    feat = r.get("特征", "") or ""
    res = calc(name, unit, ctrl, feat)
    if res is None:
        unmatched.append(r)
        continue
    u, w, x, y, note = res
    t_new = u + w + x + y
    ratio = (t_new * 1.12 / ctrl) if ctrl else None
    newdiff = round((ratio - 1) * 100, 1) if ratio else None
    out.append({
        "文件": r["文件"], "行": r["行"], "sheet": r.get("sheet", ""),
        "项目名称": name, "单位": unit,
        "工程量": r["工程量"], "控制价": ctrl,
        "现成本": r["成本"], "现主材": r["主材U"], "现人工": r["人工W"],
        "现辅材": r["辅材X"], "现机械": r["机械Y"], "现差异%": r["差异%"],
        "新主材": u, "新人工": w, "新辅材": x, "新机械": y,
        "新成本": round(t_new, 2), "新成本x1.12": round(t_new * 1.12, 2),
        "新差异%": newdiff, "分析": note,
        "兜底": "Y" if "按控制价拆分" in note else "",
    })

with open(r"data\tmp\母行测算结果_全量.csv", "w", encoding="utf-8-sig", newline="") as f:
    w_csv = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w_csv.writeheader()
    for r in out:
        w_csv.writerow(r)

print(f"已测算: {len(out)}  未匹配: {len(unmatched)}")
for r in unmatched[:50]:
    print(f"  ✗ [{r['文件']}] 行{r['行']} {r['项目名称']} | {r['单位']} | 控制价{r['控制价']} 现成本{r['成本']}")

import collections
c = collections.Counter()
for r in out:
    d = r["新差异%"]
    if d is None:
        c["异常"] += 1
    elif abs(d) <= 15:
        c["±15%"] += 1
    elif abs(d) <= 30:
        c["15~30%"] += 1
    else:
        c[">30%"] += 1
print("重填后与控制价差异分布:", dict(c))
