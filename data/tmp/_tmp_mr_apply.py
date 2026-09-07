# -*- coding: utf-8 -*-
"""备份并批量修正 market_reference_prices.json 表值（确定性表值偏差）"""
import io
import json
import shutil
from pathlib import Path

CFG = Path(r'd:\projects\cost-estimation\config\market_reference_prices.json')
BAK = Path(r'd:\projects\cost-estimation\config\market_reference_prices.json.bak_mrfix')
LOG = Path(r'd:\projects\cost-estimation\data\tmp\_tmp_mr_apply_out.txt')

# rule_id -> {field: new_value}  仅确定性表值偏差（判=当前、成功行少/实值一致）
UPDATES = {
    'zh_shaped_ceiling': {'labor': 70.0},
    'ceiling_gypsum': {'material_main': 0.0, 'labor': 70.0},
    'fan_coil_7kw': {'material_main': 5800.0, 'labor': 350.0},
    'breaker_nm1_generic': {'material_main': 240.35, 'labor': 103.15},
    'aluminum_skirting': {'labor': 15.0},
    'gate_valve': {'material_main': 39.48, 'labor': 46.83},
    'hvac_fcu_medium': {'material_main': 2044.74, 'labor': 826.96},
    'network_switch': {'material_main': 1638.93, 'labor': 614.25},
    'light_switch': {'material_main': 17.0},
    'window_auto_switch_sz': {'material_main': 1120.0, 'labor': 0.0},
    'glass_partition_install': {'labor': 70.0},
    'low_voltage_switchgear': {'material_main': 992.0, 'labor': 775.0},
    'hvac_fan': {'material_main': 1597.05, 'labor': 947.24},
    'tile_600_floor': {'material_main': 33.0, 'labor': 40.0},
    'ceiling_bracing': {'material_main': 35.60, 'labor': 45.0},
    'terrazzo_tile_light_sz': {'material_main': 81.71, 'labor': 46.06},
    'backfill_ceramsite_sump': {'labor': 10.5},
    'air_curtain_electric': {'material_main': 1225.89},
    'zh_stone_wall_dry_wave': {'material_main': 375.50},
    'translucent_film_ceiling': {'material_main': 230.0, 'labor': 80.0},
    'fire_inspection_fee_sz': {'material_main': 1500.0, 'labor': 990.0},
    'fan_coil_8kw_review': {'material_main': 1850.09},
    'hvac_duct_check_valve': {'material_main': 128.24, 'labor': 66.14},
    'evacuation_sign_light': {'material_main': 85.0},
    'marble_secret_door_st02': {'material_main': 448.0, 'labor': 409.64},
    'waste_bin': {'labor': 51.30},
    'sanitary_hand_dryer': {'labor': 119.25},
    'ceiling_access_panel': {'material_main': 45.23, 'labor': 40.20},
    'emergency_light': {'material_main': 75.90},
    'weak_rack': {'material_main': 924.77},
    'network_cable_cat6': {'material_main': 2.61},
    'pressure_test': {'material_main': 400.0, 'labor': 380.0},
    'smoke_exhaust_debug_sz': {'material_main': 600.0, 'labor': 570.0},
    'aluminum_canopy': {'material_main': 465.0, 'labor': 103.38},
    'fire_damper': {'material_main': 181.02},
    'sz_bathroom_sunken_waterproof': {'material_main': 37.13},
    'waste_bin_paper': {'material_main': 16.0},
    'sanitary_toilet_cleaner': {'material_main': 34.0, 'labor': 32.30},
    'sanitary_coat_hook': {'labor': 6.45},
    'toilet_partition_urinal': {'material_main': 834.78, 'labor': 185.51},
    'chasing': {'material_main': 0.0, 'labor': 19.36},
    'plumbing_valve': {'labor': 25.06},
    'faucet_set': {'material_main': 465.0},
    'floor_drain': {'material_main': 55.0, 'labor': 25.0},
    'fire_alarm_button': {'material_main': 44.30, 'labor': 34.09},
    'gate_valve_dn50': {'material_main': 92.40, 'labor': 68.14},
    'carpet_floor_block': {'material_main': 260.0, 'labor': 80.0},
    'ceiling_suspended': {'material_main': 157.32},
    'curtain': {'material_main': 34.85, 'labor': 85.72},
    'lighting_cove': {'material_main': 146.81, 'labor': 159.27},
    'light_switch_generic': {'material_main': 27.0},
    'wood_veneer_panel': {'material_main': 580.0},
    'metal_railing_new': {'material_main': 335.0, 'labor': 50.0},
    'tile_wall_adhesive_ct': {'material_main': 91.23, 'labor': 84.59},
    'glass_mirror': {'material_main': 192.5, 'labor': 67.5},
    'electrical_panel_box': {'material_main': 1297.49},
    'ip_camera': {'material_main': 611.90, 'labor': 259.35},
    'ac_outdoor_unit': {'material_main': 20550.44},
}

cfg = json.loads(CFG.read_text(encoding='utf-8'))
rules = {r['id']: r for r in cfg['rules']}

buf = ['备份: %s' % BAK]
shutil.copy2(CFG, BAK)

changed = 0
for rid, fields in UPDATES.items():
    r = rules.get(rid)
    if r is None:
        buf.append('!! 未找到规则: %s' % rid)
        continue
    for f, v in fields.items():
        old = r.get(f, 0)
        if abs(old - v) > 1e-9:
            r[f] = v
            buf.append('%-32s %-14s %s -> %s' % (rid, f, old, v))
            changed += 1

CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
buf.append('\n共修改 %d 个字段，写入 %s' % (changed, CFG))
LOG.write_text('\n'.join(buf), encoding='utf-8')
print('done, changed=%d' % changed)
