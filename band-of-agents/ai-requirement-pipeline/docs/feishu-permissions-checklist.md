# 飞书权限 & 事件订阅清单
> 适用系统：AI企业提效数字团队（6-Agent Pipeline）
> 整理时间：2026-05-08
> 最后更新：2026-05-09（切换至 Bao 2 bot）

---

## 零、当前 Bot 信息（Hackathon 专用）

| 项目 | 值 |
|------|----|
| App ID | `cli_a97062d288f91cb1` |
| App Secret | `CBShdaiECOJ23JbfpbVsT2dq5Ev1YBKN` |
| Bot 名称 | Bao 2 |
| Bot open_id | `ou_7bea69adf322b9fefb4569b84edd2f2d` |
| Jacky open_id（Bao 2 下） | `ou_09fedf552e148463378008c54453ebb8` |
| 激活状态 | ✅ 已激活（activate_status=2） |

> ⚠️ 注意：Jacky 在不同 bot 下的 open_id 不同。
> - Sleeper (main bot) 下：`ou_6b5a125571126eec0737c327c493254e`
> - Bao 2 下：`ou_09fedf552e148463378008c54453ebb8`（2026-05-09 验证）

---

## 一、API 权限（Scopes）— 实际状态

### 消息发送

| 权限名 | 说明 | 用途 | 状态 |
|--------|------|------|------|
| `im:message` | 读取和发送私信及群消息 | 发送追问/通知/拦截告警 | ✅ 已验证可用（2026-05-09） |
| `im:message:send_as_bot` | 以应用身份发消息 | 与 im:message 三选一即可 | ✅ 已开通 |
| `im:resource` | 上传/下载消息资源 | 发送图片、文件类附件 | ✅ 已开通 |

### 用户查询

| 权限名 | 说明 | 用途 | 状态 |
|--------|------|------|------|
| `contact:user.id:readonly` | 查询用户 open_id | 通过邮箱/名字找到目标收件人 | ❌ 未开通（已开的是 employee_id，不是此权限） |
| `contact:user.employee_id:readonly` | 查询用户 employee_id | — | ✅ 已开通（但 Pipeline 用不上） |
| `contact:user.base:readonly` / `contact:contact.base:readonly` | 查询用户基本信息 | 查姓名/部门 | ✅ 已开通 |
| `contact:user.email:readonly` | 获取用户邮箱 | 通过邮箱反查 open_id | ❓ 未验证 |

### 群聊相关

| 权限名 | 说明 | 用途 | 状态 |
|--------|------|------|------|
| `im:chat:readonly` | 读取群信息 | 查群聊 chat_id | ✅ 已验证（bot 暂未加入任何群） |
| `im:chat.members:read` | 读取群成员列表 | 从群里查成员 open_id | ❓ 未验证 |

### 多维表格（状态中枢）

| 权限名 | 说明 | 用途 | 状态 |
|--------|------|------|------|
| `bitable:app` | 读写多维表格 | AI 代 PM 写需求状态 | ❌ 未开通（API 返回 99991672） |
| `base:app:create` | 创建多维表格应用 | 新建状态中枢表 | ❌ 未开通 |
| `base:record:create` | 创建记录 | 守门 Agent 通过后自动建行 | ❓ 依赖 bitable:app |
| `base:record:update` | 更新记录 | 各环节更新状态字段 | ❓ 依赖 bitable:app |

---

## 二、待补开权限（必须）

以下权限需在 [开发者后台](https://open.feishu.cn/app/cli_a97062d288f91cb1) → 权限管理 中搜索并开通：

| 权限名 | 优先级 | 原因 |
|--------|--------|------|
| `bitable:app` | 🔴 P0 | 没有就不能读写多维表格 |
| `contact:user.id:readonly` | 🟡 P1 | 按 open_id 查用户；Demo 里 hardcode open_id 可绕过 |

---

## 三、Demo 阶段临时方案（绕过未开通权限）

由于 `contact:user.id:readonly` 未开通，Demo 期间使用 `people_map.py` 硬编码：

```python
# pipeline/people_map.py
# Demo 阶段：所有角色统一发给 Jacky（Bao 2 下的 open_id）
PEOPLE_MAP = {
    "PM":       "ou_09fedf552e148463378008c54453ebb8",
    "研发负责人": "ou_09fedf552e148463378008c54453ebb8",
    "测试负责人": "ou_09fedf552e148463378008c54453ebb8",
    "售前":     "ou_09fedf552e148463378008c54453ebb8",
    "产品负责人": "ou_09fedf552e148463378008c54453ebb8",
}
```

---

## 四、需要订阅的事件

| 事件名 | 说明 | 用途 | 状态 |
|--------|------|------|------|
| `im.message.receive_v1` | 接收消息事件 | Human-in-the-loop：售前/PM 在飞书回复后触发 Pipeline 继续 | ❌ Demo 阶段跳过，用 Mock 模拟 |
| `im.message.message_read_v1` | 消息已读事件 | 确认关键通知已被看到 | ❌ 可选，暂不接 |

> 事件订阅地址（生产用）：`http://10.60.232.87:18789/feishu/{accountId}/events`（内网）
> Demo 阶段无需配置，Pipeline 跑完自动继续（Mock 确认）。

---

## 五、机器人可用范围

- 路径：开发者后台 → 应用版本 → 版本管理与发布 → 可用范围
- Demo 阶段建议：设为「全员」或至少包含你自己
- 当前状态：通讯录里可见 1 个用户（Jacky）

---

## 六、验证记录

| 时间 | 操作 | 结果 |
|------|------|------|
| 2026-05-09 13:38 | 发消息给 `ou_09fedf552e148463378008c54453ebb8` | ✅ 成功，Jacky 飞书收到 |
| 2026-05-09 13:48 | 新建 bitable | ❌ 权限不足（bitable:app 未开） |
| 2026-05-09 13:47 | 查询用户 open_id | ❌ 权限不足（contact:user.id:readonly 未开） |
| 2026-05-09 13:38 | 查群列表 | ✅ 成功（暂无群） |
