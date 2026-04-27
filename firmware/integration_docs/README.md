# v2.0.0 STM32 协处理器重构文档索引

> 目的：保留少量真源文档，避免多个历史计划同时声明“当前状态”。

## 当前结论

- 当前工作分支：`v2.0.0-refactor`
- 当前最新提交：`77f68a1 style: fix v2 integration doc whitespace`
- 主分支合并状态：`main` 已撤回 `f7cab6a`，当前通过 `e048fff` 保持代码内容回到合并前。
- 重新合入策略：先在 `v2.0.0-refactor` 通过完整检查，再在 `main` 上恢复合入；由于 `main` 已有 merge + revert 历史，后续不能只做普通 merge。

## 阅读顺序

1. [IMPLEMENTATION_STATUS.md](./IMPLEMENTATION_STATUS.md)
2. [STM32_COPROC_REFACTOR_PLAN.md](./STM32_COPROC_REFACTOR_PLAN.md)
3. [STM32_UART_PROTOCOL.md](./STM32_UART_PROTOCOL.md)
4. [IMPLEMENTATION_TODO.md](./IMPLEMENTATION_TODO.md)
5. [HIL_TEST_PLAN.md](./HIL_TEST_PLAN.md)
6. [RISK_REGISTER.md](./RISK_REGISTER.md)
7. [adr/](./adr)

## 文档职责

- `IMPLEMENTATION_STATUS.md`
  - 当前代码、检查结果、合并门禁的唯一状态入口。
- `STM32_COPROC_REFACTOR_PLAN.md`
  - ESP32 / STM32 职责边界和系统设计真源。
- `STM32_UART_PROTOCOL.md`
  - 板内 UART 帧格式、消息号、字段语义真源。
- `IMPLEMENTATION_TODO.md`
  - 下一批未完成事项和重新合入前必须满足的条件。
- `HIL_TEST_PLAN.md`
  - mock、build、format、bench、串口联调的测试流程和固定清单。
- `RISK_REGISTER.md`
  - 当前仍需跟踪的技术风险。
- `adr/`
  - 已冻结的关键设计决策。

## 已移除的过期文档

- `BRANCH_WORKTREE_PLAN.md`
  - 已不再作为主线合并依据；当前合并状态以本索引和 `IMPLEMENTATION_STATUS.md` 为准。
- `FIELD_REVIEW_TODO.md`
  - bench 清单已并入 `HIL_TEST_PLAN.md`。
- `TDD_EXECUTION_PLAN.md`
  - 早期 Red/Green 计划已过期；当前验证入口以 `HIL_TEST_PLAN.md` 和 CI 门禁为准。

## 重新合入前检查

在 `v2.0.0-refactor` 上至少跑通：

```powershell
git diff --check 5929987..HEAD
python -m pytest tools\tests
powershell -ExecutionPolicy Bypass -File C:\Users\50533\.codex\skills\watche-dual-mcu-bringup\scripts\run-dual-mcu-bringup.ps1 -SkipStm32Build -SkipStm32Flash -SkipEsp32Flash -SkipSession
```

并对 CI 涉及的 C/H 变更执行：

```powershell
$clang = 'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\Llvm\bin\clang-format.exe'
$files = git diff --name-only 5929987..HEAD -- firmware/s3/components firmware/s3/main | Where-Object { $_ -match '\.(c|h)$' }
& $clang --dry-run --Werror @files
```

## 写作规则

- 协议字段只写在 `STM32_UART_PROTOCOL.md`。
- 系统职责边界只写在 `STM32_COPROC_REFACTOR_PLAN.md`。
- 当前状态只写在 `IMPLEMENTATION_STATUS.md`。
- 后续工作只写在 `IMPLEMENTATION_TODO.md`。
- bench 和验证流程只写在 `HIL_TEST_PLAN.md`。
