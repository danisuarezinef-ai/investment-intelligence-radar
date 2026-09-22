# CEO Android DEV signing key

This key is intentionally public and is valid only for the laboratory/debug package `ai.ceo.android.dev`.

- Alias: `ceo-dev-lab`
- Store/key password: `ceo-dev-lab-only`
- PKCS12 SHA-256: `1ef240f8d0f5a1b4e540c0d13b746c8cccee2cbd7b28b88a7c9cf5e67629c3d1`
- Certificate SHA-256: `EF32DA1C6E0F96654342F8B0CEFE86089AAA0E5B454C396C69F36382AFA9F6B3`

It MUST NOT sign `ai.ceo.android` stable/release builds.

Purpose: allow CI-built DEV APKs to update one another so the in-app update path can be proven before the private release-signing authority is initialized.
