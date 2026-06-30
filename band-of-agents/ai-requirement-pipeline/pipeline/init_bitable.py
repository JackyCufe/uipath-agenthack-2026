"""
init_bitable.py — 初始化多维表格

按 demo.py 当前真实写入契约创建新表。
运行一次即可，之后更新 config.py 里的 BITABLE_TABLE_ID。

用法：
  cd pipeline
  python init_bitable.py
"""
import sys
import time
import json
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BASE_URL, BITABLE_APP_TOKEN


# ─── 飞书 Token ──────────────────────────────────────────

def _get_token() -> str:
    resp = requests.post(
        f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
    )
    return resp.json()["tenant_access_token"]


# ─── 字段定义（按 demo.py 契约）──────────────────────────

# Feishu Bitable field types
TEXT = 1
NUMBER = 2
SELECT = 3
PERSON = 11
DATE = 5

FIELDS = [
    # ── 基础信息（9）
    ("需求ID", TEXT),
    ("需求标题", TEXT),
    ("客户名称", TEXT),
    ("创建时间", DATE),
    ("当前阶段", SELECT, [
        "Stage1 售前录入",
        "Stage2 产品审批",
        "Stage3 研发审批",
        "Stage4 发版审批",
        "Stage5 客户反馈",
        "Stage6 复盘",
        "已终止",
        "退回PM重评估",
    ]),
    ("当前负责人", PERSON),
    ("总拒绝次数", NUMBER),
    ("最后更新时间", DATE),
    ("终止原因", TEXT),

    # ── Stage 1（8）
    ("S1_负责人", PERSON),
    ("S1_客户是谁", TEXT),
    ("S1_使用场景", TEXT),
    ("S1_遇到的问题", TEXT),
    ("S1_期望结果", TEXT),
    ("S1_需求类型", TEXT),
    ("S1_交互轮数", NUMBER),
    ("S1_返工次数", NUMBER),
    ("S1_提交时间", DATE),
    ("S1_结果", SELECT, ["通过", "已终止"]),

    # ── Stage 2（15）
    ("S2_负责人", PERSON),
    ("S2_收单时间", DATE),
    ("S2_决策时间", DATE),
    ("S2_耗时_分钟", NUMBER),
    ("S2_结果", SELECT, ["通过", "拒绝", "撤回"]),
    ("S2_拒绝原因", TEXT),
    ("S2_核心价值", TEXT),
    ("S2_功能定义", TEXT),
    ("S2_优先级", SELECT, ["SP", "P0", "P1", "P2"]),
    ("S2_验收标准原文", TEXT),
    ("S2_结构化验收标准", TEXT),
    ("S2_测试用例", TEXT),
    ("S2_预计影响用户数", NUMBER),
    ("S2_补充说明", TEXT),
    ("S2_二次确认退回次数", NUMBER),
    ("S2_返工次数", NUMBER),

    # ── Stage 3（11）
    ("S3_负责人", PERSON),
    ("S3_收单时间", DATE),
    ("S3_决策时间", DATE),
    ("S3_耗时_分钟", NUMBER),
    ("S3_结果", SELECT, ["通过", "拒绝"]),
    ("S3_拒绝原因", TEXT),
    ("S3_技术方案", TEXT),
    ("S3_工作量_人天", NUMBER),
    ("S3_风险点", TEXT),
    ("S3_客户场景自测结论", SELECT, ["通过", "部分通过", "未通过"]),
    ("S3_自测备注", TEXT),
    ("S3_返工次数", NUMBER),

    # ── Stage 4（12）
    ("S4_负责人", PERSON),
    ("S4_收单时间", DATE),
    ("S4_决策时间", DATE),
    ("S4_耗时_分钟", NUMBER),
    ("S4_结果", SELECT, ["通过", "拒绝"]),
    ("S4_拒绝原因", TEXT),
    ("S4_本版核心价值", TEXT),
    ("S4_版本号", TEXT),
    ("S4_计划发版日期", DATE),
    ("S4_客户场景是否跑通", SELECT, ["是", "否"]),
    ("S4_发版风险", SELECT, ["低", "中", "高"]),
    ("S4_回滚方案", TEXT),

    # ── Stage 5（8）
    ("S5_负责人", PERSON),
    ("S5_问卷内容", TEXT),
    ("S5_分发时间", DATE),
    ("S5_反馈提交时间", DATE),
    ("S5_满意度均分", NUMBER),
    ("S5_反馈摘要", TEXT),
    ("S5_结果", SELECT, ["问卷已确认", "反馈已录入"]),
    ("S5_满意度脚本计算值", NUMBER),

    # ── Stage 6 / 复盘（4）
    ("S6_ROI结论", TEXT),
    ("S6_流程健康度", NUMBER),
    ("S6_复盘报告", TEXT),
    ("S6_复盘发送时间", DATE),
]

assert len(FIELDS) == 71, f"字段总数应为 71，实际 {len(FIELDS)}"


def _build_field_payload(name: str, field_type: int, options: list[str] | None = None) -> dict:
    body: dict = {"field_name": name, "type": field_type}

    if field_type == SELECT and options:
        body["property"] = {
            "options": [{"name": opt} for opt in options]
        }
    elif field_type == DATE:
        body["property"] = {
            "date_formatter": "yyyy-MM-dd HH:mm",
            "auto_fill": False,
        }
    elif field_type == PERSON:
        body["property"] = {
            "multiple": False,
        }

    return body


# ─── 主流程 ─────────────────────────────────────────────

def main():
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print(f"[init_bitable] App token: {BITABLE_APP_TOKEN}")

    # 1. 在当前 App 下创建新表
    print("[init_bitable] 创建新表...")
    resp = requests.post(
        f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables",
        headers=headers,
        json={"table": {"name": f"AI需求管理Pipeline v5 {time.strftime('%m%d-%H%M%S')}"}},
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"[init_bitable] ❌ 创建表失败: {data.get('msg')}")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        sys.exit(1)

    table_id = data["data"]["table_id"]
    print(f"[init_bitable] ✅ 新表创建成功: table_id={table_id}")

    # 2. 删除飞书自动创建的默认字段（默认有「多行文本」字段，不需要）
    time.sleep(0.5)
    resp_fields = requests.get(
        f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{table_id}/fields",
        headers=headers,
    )
    existing = resp_fields.json().get("data", {}).get("items", [])
    default_field_ids = [f["field_id"] for f in existing]
    print(f"[init_bitable] 现有默认字段 {len(default_field_ids)} 个，准备替换...")

    # 3. 逐个创建字段
    created = 0
    for field in FIELDS:
        time.sleep(0.15)
        if len(field) == 2:
            name, ftype = field
            options = None
        else:
            name, ftype, options = field

        body = _build_field_payload(name, ftype, options)
        r = requests.post(
            f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{table_id}/fields",
            headers=headers,
            json=body,
        )
        d = r.json()
        if d.get("code") != 0:
            print(f"  ❌ 创建字段「{name}」失败: {d.get('msg')}")
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            created += 1
            if created % 10 == 0:
                print(f"  [{created}/{len(FIELDS)}] 已创建...")

    print(f"[init_bitable] ✅ 共创建 {created}/{len(FIELDS)} 个字段")

    # 4. 删除默认字段
    deleted = 0
    for fid in default_field_ids:
        time.sleep(0.15)
        r = requests.delete(
            f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{table_id}/fields/{fid}",
            headers=headers,
        )
        d = r.json()
        if d.get("code") == 0:
            deleted += 1

    print(f"[init_bitable] 删除默认字段 {deleted}/{len(default_field_ids)} 个")
    print()
    print("=" * 60)
    print("✅ 初始化完成！")
    print(f"   新 BITABLE_TABLE_ID = {table_id!r}")
    print()
    print("   请更新 config.py：")
    print(f"   BITABLE_TABLE_ID = os.environ.get(\"BITABLE_TABLE_ID\", \"{table_id}\")")
    print("=" * 60)


if __name__ == "__main__":
    main()
