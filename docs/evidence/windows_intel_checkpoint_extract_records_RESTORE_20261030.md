# Elysia Windows Intelligence Checkpoint Restore (extract-records)

Source branch: cursor/windows-extract-records-20261030
Source SHA: 1a1af2e4c00eab8f2a9b3c7d0c5eca3b80be118e
Bundle: D:\ElysiaBackups\windows-intel-checkpoint-extract-records-20261030\elysia-windows-extract-records-1a1af2e.bundle
Bundle SHA256: 3a8683401c26e623fe6a15f21764fe6e01554acee5834060e1ba283b5cc441fd

Prior verified bundle (preserved): D:\ElysiaBackups\windows-intel-checkpoint-20261030\elysia-windows-structured-field-extraction-de47c45.bundle (de47c45)

## Verify
```
git bundle verify "D:\ElysiaBackups\windows-intel-checkpoint-extract-records-20261030\elysia-windows-extract-records-1a1af2e.bundle"
```

## Restore into disposable directory
```
git -c safe.directory=* clone -b cursor/windows-extract-records-20261030 "D:\ElysiaBackups\windows-intel-checkpoint-extract-records-20261030\elysia-windows-extract-records-1a1af2e.bundle" elysia-restore-test
cd elysia-restore-test
git -c safe.directory=* rev-parse HEAD
# Expected: 1a1af2e4c00eab8f2a9b3c7d0c5eca3b80be118e
```

Restore verification: restored_sha=1a1af2e matches_source=True key_files_intact=True blobs_match=True
Do not push or merge without operator authorization. Backup is on D: ESD-USB (not cloud).
