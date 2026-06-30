import os
from pathlib import Path

# ── 加载 .env 文件 ────────────────────────────────────────
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())
    print(f"[config] 加载: .env")
else:
    print(f"[config] ⚠️ 找不到 .env，使用系统环境变量")

# ── LLM Provider ──────────────────────────────────────────
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "deepseek").lower()

# LiteLLM Proxy（兼容旧配置）
LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:4000")
LITELLM_API_KEY  = os.environ.get("LITELLM_API_KEY", "sk-openclaw-local")

# DeepSeek API
DEEPSEEK_API_KEY  = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL    = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# 统一模型名
if LLM_PROVIDER == "deepseek":
    MODEL = DEEPSEEK_MODEL
else:
    MODEL = os.environ.get("MODEL", "claude-sonnet-4-6")

# Feishu
FEISHU_APP_ID     = os.environ.get("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
FEISHU_BASE_URL   = "https://open.feishu.cn/open-apis"

# Bitable
BITABLE_URL       = os.environ.get("BITABLE_URL", "")
BITABLE_APP_TOKEN = os.environ.get("BITABLE_APP_TOKEN")
BITABLE_TABLE_ID  = os.environ.get("BITABLE_TABLE_ID")
KB_TABLE_ID        = os.environ.get("KB_TABLE_ID", "")

# User
JACKY_OPEN_ID = os.environ.get("JACKY_OPEN_ID", "")

# Bot1 —客户路由Bot
BOT1_APP_ID = os.environ.get("BOT1_APP_ID", "")
BOT1_APP_SECRET = os.environ.get("BOT1_APP_SECRET", "")
BOT1_JACKY_OPEN_ID = os.environ.get("BOT1_JACKY_OPEN_ID", "")
BOT1_CHAT_ID = os.environ.get("BOT1_CHAT_ID", "")

# Demo mode: False = 真实飞书 API；True = 只打印到控制台
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"

# Paths
AGENTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../agents"))
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data"))

# 售后群 chat_id — Stage4发版后通知群
AFTERSALES_GROUP_CHAT_ID = os.environ.get("AFTERSALES_GROUP_CHAT_ID", "")

# ── 双层存储配置 ───────────────────────────────────────────

# Wiki 空间ID — DualLayerStorage 的 Wiki 内容层写入目标
WIKI_SPACE_ID = os.environ.get("WIKI_SPACE_ID", "")

# 检索索引字段（Bitable 列名，需在 Bitable 表中预先创建）
INDEX_FIELDS = {
    "keyword_tags":     "keyword_tags",       # TEXT — 检索关键词
    "embedding_vector": "embedding_vector",   # TEXT — JSON向量
    "searchable_text":  "searchable_text",    # TEXT — embedding源文本
    "wiki_token":       "wiki_token",         # URL  — Wiki链接
    "last_updated":     "最后更新时间",        # DATE — 索引刷新时间
    "stage_verdict":    "stage_verdict",      # TEXT — 阶段+判定摘要
}

# 语义检索配置
SEARCH_TOP_K = int(os.environ.get("SEARCH_TOP_K", "3"))       # 返回TopK
SEARCH_KEYWORD_LIMIT = int(os.environ.get("SEARCH_KEYWORD_LIMIT", "20"))  # keyword过滤候选数
