# LLM 手机任务助手接入说明

## 架构

本功能不把 LLM API Key 放进 Flutter App，也不把大模型部署到小车。

```text
Flutter App 聊天页
-> POST /api/llm/tasks/plan
-> 后端 LLM/规则规划器生成任务计划
-> App 展示计划和安全提示
-> 用户点击确认
-> POST /api/llm/tasks/{plan_id}/execute
-> 后端按工具白名单调用 MQTT/车队接口
-> 小车 robot_agent ACK
```

安全原则：

- LLM 只能生成计划，不能直接发 `/cmd_vel`。
- 后端只执行白名单工具。
- 运动类任务必须用户确认。
- 后端执行前会检查小车 readiness。
- 可以随时通过 `fleet.safety_stop` 停车。

## 后端配置

真实 API Key 只放在 `backend/.env`，不要提交到仓库：

```env
LLM_API_BASE=https://你的-openai-compatible-base-url/v1
LLM_API_KEY=你的-api-key
LLM_MODEL=你的模型名
```

当前默认模型使用 `gpt-5.4-mini`，用于控制 token 成本；如需更强模型，只建议在复杂任务调试时临时切换。

注意：Codex/ChatGPT 内部正在使用的 API Key 不会暴露给项目代码。这里必须填写你自己的 OpenAI-compatible 网关地址和 Key；如果为空，系统会安全地使用规则兜底。

`LLM_API_BASE` 也可以直接填写完整 chat completions 地址，例如：

```env
LLM_API_BASE=https://你的服务地址/v1/chat/completions
```

如果没有配置 `LLM_API_BASE` 或 `LLM_API_KEY`，后端会自动使用规则兜底模式，仍可完成以下演示：

- “查询 robot_001 是否在线”
- “急停 robot_001”
- “让 robot_001 核验 B2 消防通道的沪A12345”
- “护送 robot_001 返回维修区”

## 后端接口

查询 LLM 运行状态，不返回 API Key：

```http
GET /api/llm/status
```

返回示例：

```json
{
  "llm_configured": false,
  "api_base_host": null,
  "model": "gpt-5.4-mini",
  "planner_mode": "rule_fallback",
  "message": "未配置 LLM_API_BASE 或 LLM_API_KEY，当前使用规则兜底。"
}
```

查询工具白名单：

```http
GET /api/llm/tools
```

可带小车编号查询当前可用性：

```http
GET /api/llm/tools?robot_codes=robot_001
```

返回中的关键字段：

```json
{
  "name": "fleet.plate_verify",
  "backend_route": "POST /api/fleet/vision/plate/verify",
  "command_name": "plate_verify_scan",
  "required_arguments": ["verifier_robot_code", "plate_number"],
  "safety_level": "motion_command",
  "readiness_required": true,
  "requires_confirmation": true,
  "available": false,
  "unavailable_reason": "not all target robots are ready"
}
```

这就是 LLM “知道有哪些接口”的来源：后端把这份工具清单放进 prompt，LLM 只能返回其中的 `name` 和参数。后端收到结果后还会再校验：

- 工具名必须存在于白名单。
- 必填参数必须齐全。
- 运动类工具必须用户确认。
- 需要 readiness 的工具在执行前还会再次检查小车状态。
- MQTT 发布失败会作为真实执行结果返回，不由 LLM 猜测成功。

自然语言生成计划：

```http
POST /api/llm/tasks/plan
```

请求示例：

```json
{
  "message": "让 robot_001 核验 B2 消防通道的沪A12345",
  "robot_codes": ["robot_001"],
  "allow_llm": true,
  "auto_execute": false
}
```

执行已确认计划：

```http
POST /api/llm/tasks/{plan_id}/execute
```

请求示例：

```json
{
  "confirmed": true
}
```

## App 页面

入口：

```text
底部导航 -> 助手
```

页面行为：

- 用户像 ChatGPT 一样输入自然语言任务。
- App 调后端生成计划，不直接调用 LLM API。
- 助手气泡中展示任务步骤、安全级别、参数和安全提示。
- 用户点击“确认并执行”后，App 调后端执行计划。
- 执行结果会以新的助手气泡展示。

## 第一版支持的工具

```text
fleet.summary       只读，查询车队总览
fleet.readiness     只读，检查小车是否 ready
fleet.safety_stop   安全命令，急停/停止
fleet.plate_verify  运动命令，低速原地扫描核验车牌
fleet.escort_return 运动命令，短时低速护送返航
```

## 本地验证

后端启动：

```powershell
cd F:\SHIXUN\car10th\backend
python -m uvicorn apps.web_api.main:app --host 0.0.0.0 --port 8000
```

App 确认 API 地址指向后端，例如：

```text
http://192.168.137.51:8000
```

如果要真机执行运动类任务，先确认：

```powershell
curl.exe -s http://127.0.0.1:8000/api/fleet/robots
curl.exe -s http://127.0.0.1:8000/api/fleet/summary
```

并先测试：

```text
急停 robot_001
```
