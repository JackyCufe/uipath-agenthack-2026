"""
upgrade_bitable_fields.py — 把现有表的字段升级为正确类型

把文本(1)字段升级为：
  - 单选(3): 当前阶段、各阶段结果、优先级、自测结论等
  - 日期(5): 所有时间字段
  - 人员(11): 所有负责人字段

实现方式：删旧字段 + 重新创建（飞书不支持直接改类型）
因为表是空表，零数据风险。

用法：
  cd pipeline
  python upgrade_bitable_fields.py
"""
import sys
import time
import json
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BASE_URL, BITABLE_APP_TOKEN, BITABLE_TABLE_ID

# ─── 类型常量 ───────────────────────────────────────────
TEXT   = 1
NUMBER = 2
SELECT = 3   # 单选
DATE   = 5   # 日期
PERSON = 11  # 人员

# ─── 需要升级的字段定义 ─────────────────────────────────
# 格式: (字段名, 新类型, 选项列表(仅单选需要))

UPGRADES = [
    # ── 人员字段 (11)
    ("当前负责人",           PERSON, None),
    ("S1_负责人",            PERSON, None),
    ("S1_下一级负责人",      PERSON, None),
    ("S2_负责人",            PERSON, None),
    ("S2_下一级负责人",      PERSON, None),
    ("S3_负责人",            PERSON, None),
    ("S3_下一级负责人",      PERSON, None),
    ("S4_负责人",            PERSON, None),
    ("S5_负责人",            PERSON, None),

    # ── 单选字段 (3)
    ("当前阶段", SELECT, [
        "Stage1 售前录入",
        "Stage2 产品审批",
        "Stage3 研发审批",
        "Stage4 发版审批",
        "Stage5 客户反馈",
        "Stage6 复盘",
        "已终止",
    ]),
    ("S1_结果", SELECT, ["通过", "已终止"]),
    ("S2_结果", SELECT, ["通过", "拒绝"]),
    ("S3_结果", SELECT, ["通过", "拒绝"]),
    ("S4_结果", SELECT, ["通过", "拒绝"]),
    ("S5_结果", SELECT, ["通过", "待处理"]),
    ("S2_优先级", SELECT, ["P0 紧急", "P1 高", "P2 中", "P3 低"]),
    ("S3_客户场景自测结论", SELECT, ["通过", "部分通过", "不通过"]),
    ("S4_客户场景是否跑通", SELECT, ["是", "否", "部分"]),
    ("ROI结论", SELECT, ["正向", "持平", "负向", "待评估"]),

    # ── 日期字段 (5)
    ("创建时间",         DATE, None),
    ("最后更新时间",     DATE, None),
    ("S1_收单时间",      DATE, None),
    ("S1_提交时间",      DATE, None),
    ("S2_收单时间",      DATE, None),
    ("S2_决策时间",      DATE, None),
    ("S3_收单时间",      DATE, None),
    ("S3_决策时间",      DATE, None),
    ("S4_收单时间",      DATE, None),
    ("S4_决策时间",      DATE, None),
    ("S4_计划发版日期",  DATE, None),
    ("S5_分发时间",      DATE, None),
    ("S5_反馈提交时间",  DATE, None),
    ("复盘发送时间",     DATE, None),
]

# ─── 飞书 Token ──────────────────────────────────────────

def _get_token() -> str:
    resp = requests.post(
        f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
    )
    return resp.json()["tenant_access_token"]


# ─── 主流程 ─────────────────────────────────────────────

def main():
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print(f"目标表: {BITABLE_TABLE_ID}")
    print(f"升级字段数: {len(UPGRADES)}")
    print()

    # 1. 拉取现有字段，建立 name→field_id 映射
    resp = requests.get(
        f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/fields",
        headers=headers,
    )
    items = resp.json().get("data", {}).get("items", [])
    field_map = {f["field_name"]: f["field_id"] for f in items}
    print(f"现有字段 {len(field_map)} 个")

    ok = 0
    fail = 0

    for field_name, new_type, options in UPGRADES:
        field_id = field_map.get(field_name)
        if not field_id:
            print(f"  ⚠️  字段「{field_name}」不存在，跳过")
            continue

        # 2. 删除旧字段
        time.sleep(0.2)
        r_del = requests.delete(
            f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/fields/{field_id}",
            headers=headers,
        )
        d_del = r_del.json()
        if d_del.get("code") != 0:
            print(f"  ❌ 删除「{field_name}」失败: {d_del.get('msg')}")
            fail += 1
            continue

        # 3. 重新创建（正确类型）
        time.sleep(0.2)
        body: dict = {"field_name": field_name, "type": new_type}
        if new_type == SELECT and options:
            body["property"] = {
                "options": [{"name": o} for o in options]
            }
        elif new_type == DATE:
            body["property"] = {
                "date_formatter": "yyyy/MM/dd HH:mm",
                "auto_fill": False,
            }

        r_create = requests.post(
            f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/fields",
            headers=headers,
            json=body,
        )
        d_create = r_create.json()
        if d_create.get("code") != 0:
            print(f"  ❌ 创建「{field_name}」({new_type})失败: {d_create.get('msg')}")
            fail += 1
        else:
            type_label = {PERSON: "人员", SELECT: "单选", DATE: "日期"}.get(new_type, str(new_type))
            print(f"  ✅ {field_name} → {type_label}")
            ok += 1

    print()
    print(f"完成：成功 {ok}，失败 {fail}，共 {len(UPGRADES)} 个")


if __name__ == "__main__":
    main()
