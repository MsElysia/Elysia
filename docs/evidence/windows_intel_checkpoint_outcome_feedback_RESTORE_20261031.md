# Elysia Windows Intelligence Checkpoint Restore (outcome-feedback)

Source branch: cursor/windows-outcome-feedback-20261031
Source SHA: 6520bd15497e7da2d36663b205be1def7a2454c1
Bundle: D:\ElysiaBackups\windows-intel-checkpoint-outcome-feedback-20261031\elysia-windows-outcome-feedback-6520bd1.bundle
Bundle SHA256: 03c0bf78a6f83a8d527b7644fcb7b3e93a7a3b74a6a68f4b9fb5f9a820d0f561

## Verify
```
git bundle verify "D:\ElysiaBackups\windows-intel-checkpoint-outcome-feedback-20261031\elysia-windows-outcome-feedback-6520bd1.bundle"
```

## Restore
```
git -c safe.directory=* clone -b cursor/windows-outcome-feedback-20261031 "D:\ElysiaBackups\windows-intel-checkpoint-outcome-feedback-20261031\elysia-windows-outcome-feedback-6520bd1.bundle" elysia-restore-test
cd elysia-restore-test
git -c safe.directory=* rev-parse HEAD
# Expected: 6520bd15497e7da2d36663b205be1def7a2454c1
```

Prior backups preserved on D: (de47c45, 1a1af2e, 4fe92b9). Do not push/merge without authorization.
