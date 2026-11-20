# collectd MQTT for Home Assistant

把 [collectd](https://collectd.org/) 的 MQTT 输出接入 Home Assistant：订阅 collectd `mqtt` 插件发布的指标，自动为每个数据源创建一个 sensor 实体，并按主机聚合成设备。

- 全自动发现：收到哪个指标就建哪个实体，无需在 YAML 里逐条声明。
- 复用 Home Assistant 已有的 MQTT 连接，不重复保存 broker 凭据。
- 按 `types.db` 还原多值指标（`load` 的三个时间窗、`df` 的 used/free、`if_octets` 的 rx/tx 等）。
- 按指标类型给出单位、device class、state class 和显示精度。
- 主机 / include / exclude 三层 glob 过滤；被排除的指标会从实体注册表移除。
- 指标停止上报或 MQTT 断连时，实体自动变为 `unavailable`。
- 中文与英文界面文案。

## 工作方式

collectd 的 `mqtt` 插件以如下主题发布数据：

```text
<Prefix>/<host>/<plugin>-<plugin_instance>/<type>-<type_instance>
```

载荷（PLAIN 格式）为：

```text
<时间戳>:<值0>[:<值1>...]
```

例如：

```text
collectd/router/interface-eth0/if_octets    1763600000.123:1234567:7654321
collectd/router/load/load                   1763600000.123:0.42:0.35:0.30
collectd/router/memory/memory-used          1763600000.123:734003200
```

集成本身不发布任何数据，也不订阅通知主题（`collectd/event/...`）。

## 前置条件

1. collectd 加载了 `mqtt` 插件，并指向 Home Assistant 使用的 broker。
2. Home Assistant 已配置 [MQTT 集成](https://www.home-assistant.io/integrations/mqtt/)。
3. Home Assistant `2026.3.0` 或更新。

## collectd 配置

在 `collectd.conf` 中：

```apache
LoadPlugin mqtt

<Plugin mqtt>
  <Publish "homeassistant">
    Host "192.0.2.10"
    Port 1883

    # 主题前缀，必须与集成里填写的值一致
    Prefix "collectd"

    # collectd 默认就是 true：DERIVE/COUNTER 以每秒速率发布
    StoreRates true

    # 建议开启：Home Assistant 重启后能立刻收到最后一次的值
    Retain true
  </Publish>
</Plugin>
```

> 只支持 PLAIN 载荷，也就是上面这种以数字开头的格式。MQTT 插件的 `Format JSON` 选项目前只存在于 collectd 的 `main` 分支，5.12.0 与 6.0.0-rc0 都没有发布，所以集成不解析 JSON。

如果 collectd 与 Home Assistant 不在同一台机器上，请按需配置 `User`、`Password`、`CACert` 等 TLS 选项。

## 安装

### HACS

1. HACS → 集成 → 右上角菜单 → **自定义仓库**。
2. 添加 `https://github.com/readonly-42894/ha-collectd-mqtt`，类别选 **Integration**。
3. 搜索 “collectd MQTT” 并安装，然后重启 Home Assistant。

### 手动安装

把 `custom_components/collectd_mqtt/` 整个目录复制到 Home Assistant 配置目录的 `custom_components/collectd_mqtt/`，然后重启。

## 配置

**设置 → 设备与服务 → 添加集成 → collectd MQTT**。

1. 填写主题前缀（默认 `collectd`）。
2. 集成会在 5 秒内试订阅 `<前缀>/#`：
   - 收到数据：直接创建集成。
   - 没收到数据：提示确认，可以选择仍然添加，方便稍后再启动 collectd。

### 选项

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| 主题前缀 | `collectd` | collectd `Publish` 块的 `Prefix`。修改它不会改变实体 ID。 |
| 主机 | 空（全部） | 每行一个 glob，匹配 collectd 的 host 段，例如 `router-*`。 |
| 包含的指标 | 空（全部） | 每行一个 glob，匹配 `<plugin>[-<plugin_instance>]/<type>[-<type_instance>]`。 |
| 排除的指标 | 空 | 同上，优先级高于“包含”。被排除的指标，其已有实体会被删除。 |
| 数值为每秒速率 | 开 | 对应 collectd 的 `StoreRates`。关闭后，计数器按累计总量处理（`total_increasing`）。 |
| 超时后置为不可用 | `180` 秒 | 超过这个时间没有新值，实体变为 `unavailable`。 |

glob 使用 `fnmatch` 语法（`*`、`?`、`[abc]`），不是 MQTT 的 `#` / `+`。示例：

```text
router-*                 # 所有以 router- 开头的主机
interface-*/if_octets    # 所有网卡的收发字节速率
*/cpu-*                  # 所有 CPU 相关指标
df-*/df_complex-*        # 所有文件系统用量
```

修改选项后集成会自动重载。

## 实体

### 命名

实体名由 `plugin`、`plugin_instance`、`type`、`type_instance` 和数据源名称拼成：众所周知、会重复的 `type` 会被省略，值为 `value` 的单值数据源不再重复。

每个家族只有主类型（`if_octets`、`disk_octets`、`df_complex`）省略 `type`。与主类型共用数据源名的其它类型（`if_packets`、`if_errors`、`if_dropped`、`disk_ops`、`df_inodes` 等）保留类型标签，因此实体名不依赖消息到达顺序。

| 主题 | 数据源 | 实体名 |
| --- | --- | --- |
| `cpu-0/cpu-user` | `value` | CPU 0 User |
| `load/load` | `shortterm` | Load Shortterm |
| `memory/memory-used` | `value` | Memory Used |
| `df-root/df_complex-used` | `value` | DF root Used |
| `interface-eth0/if_octets` | `rx` | Interface eth0 RX |
| `interface-eth0/if_octets` | `tx` | Interface eth0 TX |
| `interface-eth0/if_packets` | `rx` | Interface eth0 Packets RX |
| `interface-eth0/if_dropped` | `rx` | Interface eth0 Dropped RX |
| `disk-sda/disk_octets` | `read` | Disk sda Read |
| `disk-sda/disk_ops` | `read` | Disk sda Ops Read |
| `thermal-0/temperature` | `value` | Thermal 0 Temperature |

每个 host 对应一个设备（Manufacturer 为 `collectd`），实体 ID 形如 `sensor.router_cpu_0_user`。

### 唯一 ID

```text
<host>|<plugin>|<plugin_instance>|<type>|<type_instance>|<数据源名>
```

例如 `router|interface|eth0|if_octets||rx`。主题前缀不参与唯一 ID，改名不会产生重复实体。

### 单位与分类

集成内置了一张常见类型的画像表（来自 collectd `types.db` 的类型语义）：

| 类别 | 示例类型 | 单位 / device class |
| --- | --- | --- |
| 百分比 | `percent`, `percent_bytes` | `%` |
| 字节 | `memory`, `df_complex`, `ps_rss` | `B` / data_size |
| 字节速率 | `if_octets`, `disk_octets` | `B/s` / data_rate |
| 事件速率 | `if_packets`, `disk_ops`, `irq` | 无单位 |
| 时间 | `uptime`, `latency`, `response_time` | `s` / duration |
| 温度 / 风扇 | `temperature`, `fanspeed` | `°C` / `rpm` |
| 电学与频率 | `voltage`, `current`, `power`, `energy_wh`, `frequency` | V / A / W / Wh / Hz |
| 湿度 | `humidity` | `%` / humidity |

未收录的类型仍然会创建实体，只是不带单位，并且只在首次出现时记一条 debug 日志。`StoreRates` 关闭时，累计型指标改用原始单位并标记为 `total_increasing`，便于长期统计。

> `cpu` 类型在 collectd 里是 jiffies/s，不是百分比；百分比指标需要 collectd 的 `cpu` 插件打开 `ReportPercent`，此时类型为 `percent`。

## 仪表盘示例

`docs/dashboard.yaml` 提供了可直接粘贴到 Lovelace 的示例：指标列表、历史曲线和长期统计图。

## 故障排查

**一个实体都没有**

```bash
mosquitto_sub -v -t 'collectd/#' -C 20
```

- 没有输出：collectd 没加载 `mqtt` 插件、没连上 broker，或 `Prefix` 与集成配置不一致。
- 有输出但载荷以 `[` 开头：发布端用了 JSON 格式，本集成不支持；请保持 PLAIN（默认）。
- 主题以 `collectd/event/` 开头：那是通知，不是指标，会被忽略。

**实体变成 unavailable**

超过“超时后置为不可用”设置的秒数没有收到新值，或 MQTT 连接断开。检查 collectd 的 `Interval` 与网络连接；`Retain true` 可以让 Home Assistant 重启后立刻恢复。

**修改过滤条件后旧实体还在**

选项保存会重载集成。只有在被排除的指标再次发布时，它的实体才会被删除；如果该指标已经不再发布，可以在 **设置 → 设备与服务 → 实体** 中手动删除。

**实体 ID 与预期不同**

实体 ID 由设备名（host）与实体名生成。重命名设备或实体不会影响唯一 ID，也不会创建重复实体。

## 开发与测试

需要 Python 3.14。

```bash
uv venv --python 3.14
uv pip install -r tests/requirements.txt

uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

测试使用 `pytest-homeassistant-custom-component`，MQTT 传输层在 `tests/conftest.py` 中打桩，不会连接真实 broker。

## 许可证

MIT，见 `LICENSE`。随包附带的 `data/types.db` 来自 collectd 5.12.0（MIT），详见 `NOTICE`。
