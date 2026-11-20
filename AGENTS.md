# Agent Memory — ha-collectd-mqtt

本文件是本仓库的常驻 agent 指令，跨会话生效。它不绑定任何具体 CLI、harness 或模型。

## 项目说明

Home Assistant 自定义集成，订阅 collectd MQTT 插件发布的指标并自动创建 sensor 实体。

- 规范仓库：<https://git.o0kam1.dev/HumanlessCode/ha-collectd-mqtt>（即 `origin`）。
- GitHub 仓库 <https://github.com/duzhaokun123/ha-collectd-mqtt> 按同级仓库的惯例作为镜像：代码改动提交到规范仓库；Marketplace/HACS 目录要求 GitHub 公共仓库与正式 release。
- 只支持 collectd 的 **PLAIN** payload（`时间戳:值0[:值1...]`）。MQTT 插件的 JSON 格式仅存在于 collectd `main`，任何已发布版本（5.12.0、6.0.0-rc0）都没有该选项，因此集成不解析 JSON。
- 集成复用 Home Assistant 已配置的 MQTT 连接（`homeassistant.components.mqtt.async_subscribe`），不单独保存 broker 凭据。

目录结构：

```text
custom_components/collectd_mqtt/
  __init__.py       入口、runtime_data、订阅启动与卸载
  coordinator.py    topic 分发、样本缓存、过滤、实体登记与巡检
  parser.py         topic 与 PLAIN payload 解析
  types_db.py       collectd types.db 解析
  profiles.py       单位 / device_class / state_class 画像
  naming.py         实体名与 unique_id
  entity.py         实体基类
  sensor.py         sensor 平台与批量登记
  config_flow.py    配置流程与选项流程
  transport.py      MQTT API 薄封装（测试打桩点）
  data/types.db     随包附带的 collectd types.db（MIT，见 NOTICE）
tests/              单元测试与 HA 契约测试
docs/dashboard.yaml 仪表盘示例
```

运行环境要求：Home Assistant Core `2026.3.0` 或更新，Python 3.14。

## 工作纪律

- 每完成一个独立、可验证的步骤（功能改动、修复、清理、文档与配置更新、测试通过等）就**立即 `git commit`**，不把多个步骤攒到会话末尾一次性提交。
- 提交信息遵循 conventional commit 风格（如 `feat(parser):`、`fix:`、`refactor:`、`test:`、`docs:`、`ci:`、`chore:`、`build:`），并提供简洁正文说明动机与行为，正文约 72 列换行。
- 提交时用 `git commit --author "<模型名> <模型id@llm.invalid>"` 标明**当前正在执行这次提交的 agent/模型自身**，不要照搬别的 agent 的名字。例如：

  ```bash
  git commit --author "DeepSeek Flash <deepseek-flash@llm.invalid>" -m "$(cat <<'EOF'
  fix: 描述改动

  Co-Authored-By: opencode v2.3.2
  EOF
  )"
  ```

- `Co-Authored-By` 写实际运行的 Agent 客户端及版本（`opencode --version`），不写邮箱。
- 提交由全局 SSH 签名自动完成（`commit.gpgsign=true`、`gpg.format=ssh`），不要关闭签名。
- 任务闭环（实现完成 + 验证通过）后直接提交，无需先询问用户。
- **未获用户明确要求时，不要执行 `git push`、创建或推送标签、创建 release 或触发发布**。提交是本地整理，推送与发布由用户决定。
- 发布时单独提交 `chore: bump integration version to X.Y.Z`，只改 `manifest.json` 的 `version`，与轻量标签 `vX.Y.Z` 保持一致；如本机 `tag.gpgSign=true`，用 `git -c tag.gpgSign=false tag vX.Y.Z` 避免签名编辑器。
- 功能与修复提交不修改 `manifest.json` 的 `version`。

## 测试与验证

```bash
uv venv --python 3.14
uv pip install -r tests/requirements.txt
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

- 改动提交前必须运行 `pytest`；改动解析、命名、过滤或单位画像时补充对应单元测试。
- 测试不得访问真实 MQTT broker：`tests/conftest.py` 打桩 `custom_components.collectd_mqtt.transport`。
- 不要 mock Home Assistant 内部对象绕过契约；配置项、实体注册表与实体状态使用真实实现。
- 不提交 `.venv/`、`.cache/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/` 或测试生成的临时文件。
- 不要在测试、文档或日志中写入真实 broker 地址、用户名或令牌；示例一律用占位值。

## 代码约定

- 实体 unique ID 是持久契约：`<host>|<plugin>|<plugin_instance>|<type>|<type_instance>|<dsname>`，不含 topic 前缀。不要修改这套规则，否则会破坏用户已有的实体注册表。
- topic 前缀只属于传输层配置，选项变更不得改变 unique ID。
- 解析层（`parser.py` / `types_db.py` / `profiles.py` / `naming.py`）保持纯函数、无 HA 依赖，便于单元测试。
- 订阅回调是同步 `@callback`；解析与实体更新不得阻塞事件循环，也不要为每条消息创建任务。
- 新实体先入队、0.5 秒后批量 `async_add_entities`；不要为每条 MQTT 消息逐个登记实体。
- 未知 type、值个数与 types.db 不匹配、非 PLAIN payload 只记一次 debug 或 warning，避免刷日志。
- 遵循现有代码风格：4 空格缩进、双引号、完整类型注解、模块级 `_LOGGER`。
- 用户可见文案放在 `strings.json` 与 `translations/en.json`、`translations/zh-Hans.json`，两份翻译键结构保持一致。
- `README.md` 使用中文，描述对外行为、配置方法与实体命名规则；行为变化时同步更新。

## 不要做的事

- 不要引入额外运行时依赖（`manifest.json` 不设 `requirements`）。
- 不要再加 MQTT discovery 桥接、`binary_sensor` 或向 collectd 回写控制。
- 不要未经测试就声称验证通过。
