# people_map.py
# JACKY_OPEN_ID 从环境变量读取，由 config.py 加载对应 .env 文件注入
# 切换环境时自动切换 open_id，无需手动修改此文件
#
# sleeper 环境：ou_6b5a125571126eec0737c327c493254e（Sleeper bot 下）
# team-testing 环境：ou_53dc335c8bc5cd77a631684216a8ed48（Team Testing bot 下）
# Sleeper-J bot 下：ou_c5f5a5e3fe5d37780fa7d5d32edbce4f（飞书个人用户）

import os

# 确保 config.py 已经加载了 .env（import 顺序保证）
JACKY_OPEN_ID = os.environ.get("JACKY_OPEN_ID", "ou_6b5a125571126eec0737c327c493254e")

# Sleeper-J bot 下 Jacky 的 open_id
JACKY_SLEEPER_J_OPEN_ID = "ou_c5f5a5e3fe5d37780fa7d5d32edbce4f"

PEOPLE_MAP = {
    # 真实姓名映射（填写飞书姓名时直接命中，不走搜索 API）
    "吕嘉琪":   JACKY_OPEN_ID,
    "Jacky":   JACKY_OPEN_ID,
    "jacky":   JACKY_OPEN_ID,
    # 角色映射
    "PM":       JACKY_OPEN_ID,
    "产品经理":   JACKY_OPEN_ID,
    "研发负责人": JACKY_OPEN_ID,
    "研发":     JACKY_OPEN_ID,
    "测试负责人": JACKY_OPEN_ID,
    "售前":     JACKY_OPEN_ID,
    "售后":     JACKY_OPEN_ID,
    "产品负责人": JACKY_OPEN_ID,
}

def get_open_id(role: str) -> str:
    """根据角色名返回飞书 open_id，找不到返回 Jacky 的 ID 作为兜底。"""
    return PEOPLE_MAP.get(role, JACKY_OPEN_ID)
