"""
add_rework_fields.py — 给当前多维表格补充返工次数字段

仅新增缺失字段，不删除、不修改已有字段。

用法：
  cd pipeline
  python add_rework_fields.py
"""
import sys
import time
import json
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BASE_URL, BITABLE_APP_TOKEN, BITABLE_TABLE_ID

NUMBER = 2
FIELDS_TO_ADD = [
    ("S1_返工次数", NUMBER),
    ("S2_返工次数", NUMBER),
    ("S3_返工次数", NUMBER),
]


def _get_token() -> str:
    resp = requests.post(
        f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
    )
    return resp.json()["tenant_access_token"]


def main():
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print(f"目标表: {BITABLE_TABLE_ID}")
    resp = requests.get(
        f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/fields",
        headers=headers,
    )
    data = resp.json()
    if data.get("code") != 0:
        print(f"❌ 拉取字段失败: {data.get('msg')}")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        sys.exit(1)

    existing_names = {item["field_name"] for item in data.get("data", {}).get("items", [])}
    ok = 0
    skip = 0
    fail = 0

    for name, ftype in FIELDS_TO_ADD:
        if name in existing_names:
            print(f"  ⚠️ 已存在，跳过：{name}")
            skip += 1
            continue
        time.sleep(0.2)
        r = requests.post(
            f"{FEISHU_BASE_URL}/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/fields",
            headers=headers,
            json={"field_name": name, "type": ftype},
        )
        d = r.json()
        if d.get("code") != 0:
            print(f"  ❌ 新增字段失败：{name} -> {d.get('msg')}")
            fail += 1
        else:
            print(f"  ✅ 已新增：{name}")
            ok += 1

    print()
    print(f"完成：成功 {ok}，跳过 {skip}，失败 {fail}")


if __name__ == "__main__":
    main()
