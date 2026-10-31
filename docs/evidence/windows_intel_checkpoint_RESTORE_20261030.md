# Elysia Windows Intelligence Checkpoint Restore

Source branch: cursor/windows-structured-field-extraction-20261030
Source SHA: de47c45cc1e7cbedd1453d37d28aa2fce1738f85
Bundle: D:\ElysiaBackups\windows-intel-checkpoint-20261030\elysia-windows-structured-field-extraction-de47c45.bundle
Bundle SHA256: afb736ebf8f9a68ca3d7ccda379252f4814ed8d3a805c789e3c01f80007d4cb7

## Verify
```
git bundle verify "D:\ElysiaBackups\windows-intel-checkpoint-20261030\elysia-windows-structured-field-extraction-de47c45.bundle"
```

## Restore into disposable directory
USB volumes (ESD-USB) may lack ownership metadata. Use one-shot `-c safe.directory=*` rather than changing global git config:

```
git -c safe.directory=* clone "D:\ElysiaBackups\windows-intel-checkpoint-20261030\elysia-windows-structured-field-extraction-de47c45.bundle" elysia-restore-test
cd elysia-restore-test
git -c safe.directory=* checkout cursor/windows-structured-field-extraction-20261030
git -c safe.directory=* rev-parse HEAD
# Expected: de47c45cc1e7cbedd1453d37d28aa2fce1738f85
```

## Confirm key files
```
git -c safe.directory=* rev-parse HEAD:project_guardian/structured_field_extraction.py
git -c safe.directory=* rev-parse HEAD:project_guardian/capability_composition.py
git -c safe.directory=* rev-parse HEAD:project_guardian/conversation_continuity.py
```

Restore verification result: restored_sha=de47c45cc1e7cbedd1453d37d28aa2fce1738f85 matches_source=True key_files_intact=True blobs_match=True

Do not push or merge without operator authorization.
Backup location is on drive D: (ESD-USB), independent of system C:. This is not cloud storage. Additional offline copies recommended for disaster recovery.
