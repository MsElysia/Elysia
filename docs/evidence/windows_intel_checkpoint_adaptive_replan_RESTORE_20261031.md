# Elysia Windows Intelligence Checkpoint Restore (adaptive-replan)

Source branch: cursor/windows-adaptive-replan-20261030
Source SHA: 4fe92b9d559b5f1b5a46356c801d7538d4525f6e
Bundle: D:\ElysiaBackups\windows-intel-checkpoint-adaptive-replan-20261031\elysia-windows-adaptive-replan-4fe92b9.bundle
Bundle SHA256: 6d4549c1bd7de53244a38544404a4ca40bd455afb62051dd7f4d6302eb31773f

## Verify
```
git bundle verify "D:\ElysiaBackups\windows-intel-checkpoint-adaptive-replan-20261031\elysia-windows-adaptive-replan-4fe92b9.bundle"
```

## Restore
```
git -c safe.directory=* clone -b cursor/windows-adaptive-replan-20261030 "D:\ElysiaBackups\windows-intel-checkpoint-adaptive-replan-20261031\elysia-windows-adaptive-replan-4fe92b9.bundle" elysia-restore-test
cd elysia-restore-test
git -c safe.directory=* rev-parse HEAD
# Expected: 4fe92b9d559b5f1b5a46356c801d7538d4525f6e
```

Prior backups on D: preserved (de47c45, 1a1af2e). Do not push/merge without authorization.
