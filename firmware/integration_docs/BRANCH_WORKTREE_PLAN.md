# v2.0.0 分支与 Worktree 计划

> 目的：为 `v2.0.0` 重构建立稳定的分支和工作树安排，避免文档、ESP32、STM32、联调工具互相干扰。

## 1. 分支角色

### 1.1 主分支

- `main`
  - 稳定线
  - 不直接承接 v2 的日常开发

### 1.2 v2 集成分支

- `v2.0.0-refactor`
  - `v2.0.0` 唯一集成线
  - 文档、协议、测试、实现最终都汇入这里

### 1.3 功能分支

建议功能分支：

- `docs/v2-baseline`
- `feat/v2-protocol-core`
- `feat/v2-esp32-motion-bridge`
- `feat/v2-esp32-sensor-pipeline`
- `feat/v2-stm32-runtime-core`
- `feat/v2-hil-tools`

所有功能分支都必须从 `v2.0.0-refactor` 拉出。

## 2. 合并规则

- 不从 `main` 直接拉 v2 功能分支
- `v2.0.0-refactor` 只接收：
  - 当前阶段测试全绿
  - 文档已更新
  - 风险项已对齐
- `main` 只在 v2 集成稳定后整体合并

## 3. Worktree 布局

建议 Worktree 放在仓库外，例如：

```text
D:\GithubRep\worktrees\watcher-v2-docs
D:\GithubRep\worktrees\watcher-v2-s3
D:\GithubRep\worktrees\watcher-v2-stm32
D:\GithubRep\worktrees\watcher-v2-hil
```

### 3.1 `watcher-v2-docs`

- 分支：`docs/v2-baseline`
- 用途：协议、架构、风险、测试文档维护

### 3.2 `watcher-v2-s3`

- 分支：`feat/v2-esp32-motion-bridge` 或 `feat/v2-esp32-sensor-pipeline`
- 用途：ESP32 侧实现与适配

### 3.3 `watcher-v2-stm32`

- 分支：`feat/v2-stm32-runtime-core`
- 用途：STM32 协议实现与外设调度

### 3.4 `watcher-v2-hil`

- 分支：`feat/v2-hil-tools`
- 用途：联调脚本、故障注入、统计输出

## 4. 现阶段仓库边界

当前 `firmware/mcu` 还不是一个有效的 STM32 工程目录，只存在废弃说明文件：

- `firmware/mcu/README_DEPRECATED.md`

因此当前策略冻结为：

- 文档统一放在 `firmware/integration_docs`
- STM32 工程目录选型延后到真正建工程时再决定
- 到时单独通过 ADR 冻结是继续使用 `firmware/mcu` 还是新建 `firmware/stm32`

## 5. 每类改动的推荐落点

- 协议与文档：`docs/v2-baseline`
- 协议编解码和链路状态机：`feat/v2-protocol-core`
- 舵机/LED 适配：`feat/v2-esp32-motion-bridge`
- 传感器与背压：`feat/v2-esp32-sensor-pipeline`
- STM32 端实现：`feat/v2-stm32-runtime-core`
- 真机联调脚本：`feat/v2-hil-tools`

## 6. 评审要求

任一 PR 合并到 `v2.0.0-refactor` 前，必须明确：

- 变更属于哪个阶段
- 更新了哪份真源文档
- 对应的测试在哪一层
- 触及哪些风险项

## 7. 非目标

本计划不规定：

- GitHub PR 模板
- Code Owners
- 自动发布流程

