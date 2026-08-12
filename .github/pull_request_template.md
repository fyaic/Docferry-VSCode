## Summary

## Product boundary

- [ ] No authentication, billing, entitlement, provider key, or internal-role logic moved into the extension.
- [ ] Workspace trust, path containment, and explicit confirmation are preserved.

## Verification

- [ ] `npm ci`
- [ ] `npm audit --audit-level=high`
- [ ] `npm run build`
- [ ] `npm run test:extension`
- [ ] Platform VSIX packaging and content verification
- [ ] Documentation and privacy disclosure updated when behavior changed
