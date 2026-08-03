# Canonical Reliability Rebuild Diagnostic

- Run: `30806703800`
- Source SHA: `b147eb3268ace868751f34f325963bfc37169b26`
- UTC: `2026-08-03T10:45:02Z`

| Stage | Exit code |
|---|---:|
| Fetch backup | 0 |
| Prepare transformation | 0 |
| Canonical replacement | 0 |
| Finalize routes/navigation | 0 |
| Python compilation | 0 |
| Backend dependency install | 0 |
| Backend import/tests | 0 |
| Frontend dependency install | 0 |
| Tenant navigation tests | 0 |
| Scoped ESLint | 1 |
| Production build | 2 |

## Failure tails

### fetch

```text

```

### prepare

```text

```

### canonicalize

```text
Reliability now uses one canonical frontend and backend route surface.

```

### finalize

```text
Canonical Reliability navigation, preload and contract tests finalized.

```

### compile

```text

```

### pip

```text
Using cached sqlalchemy-2.0.44-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (3.3 MB)
Using cached svix-1.98.0-py3-none-any.whl (156 kB)
Using cached pytest-8.3.3-py3-none-any.whl (342 kB)
Using cached typing_inspection-0.4.2-py3-none-any.whl (14 kB)
Using cached typing_extensions-4.15.0-py3-none-any.whl (44 kB)
Using cached uvicorn-0.38.0-py3-none-any.whl (68 kB)
Using cached watchfiles-1.1.1-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (456 kB)
Using cached websockets-15.0.1-cp312-cp312-manylinux_2_5_x86_64.manylinux1_x86_64.manylinux_2_17_x86_64.manylinux2014_x86_64.whl (182 kB)
Using cached msgpack-1.1.2-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (427 kB)
Using cached paho_mqtt-2.1.0-py3-none-any.whl (67 kB)
Using cached tzdata-2025.2-py2.py3-none-any.whl (347 kB)
Using cached pluggy-1.6.0-py3-none-any.whl (20 kB)
Using cached attrs-26.1.0-py3-none-any.whl (67 kB)
Using cached httpx-0.28.1-py3-none-any.whl (73 kB)
Using cached httpcore-1.0.9-py3-none-any.whl (78 kB)
Using cached packaging-26.2-py3-none-any.whl (100 kB)
Using cached requests-2.34.2-py3-none-any.whl (73 kB)
Using cached charset_normalizer-3.4.9-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (224 kB)
Using cached urllib3-2.7.0-py3-none-any.whl (131 kB)
Using cached certifi-2026.7.22-py3-none-any.whl (136 kB)
Using cached argon2_cffi_bindings-25.1.0-cp39-abi3-manylinux_2_26_x86_64.manylinux_2_28_x86_64.whl (87 kB)
Using cached deprecated-1.3.1-py2.py3-none-any.whl (11 kB)
Using cached wrapt-2.3.0-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (172 kB)
Using cached et_xmlfile-2.0.0-py3-none-any.whl (18 kB)
Using cached iniconfig-2.3.0-py3-none-any.whl (7.5 kB)
Using cached python_dateutil-2.9.0.post0-py2.py3-none-any.whl (229 kB)
Using cached standardwebhooks-1.1.0-py3-none-any.whl (3.5 kB)
Installing collected packages: python-barcode, pdfrw, wrapt, websockets, urllib3, tzdata, typing_extensions, standardwebhooks, sniffio, six, PyYAML, python-multipart, python-dotenv, pypdfium2, PyMuPDF, pycparser, pyasn1, psycopg2-binary, psutil, pluggy, Pillow, paho-mqtt, packaging, msgpack, MarkupSafe, iniconfig, idna, httptools, h11, greenlet, et-xmlfile, dnspython, colorama, click, charset-normalizer, certifi, bcrypt, attrs, annotated-types, annotated-doc, uvicorn, typing-inspection, SQLAlchemy, rsa, requests, reportlab, python-dateutil, pytest, pytesseract, pydantic_core, pdf2image, openpyxl, Mako, httpcore, email-validator, ecdsa, deprecated, cffi, anyio, watchfiles, starlette, resend, python-jose, pydantic, httpx, cryptography, argon2-cffi-bindings, alembic, svix, fastapi, argon2-cffi

Successfully installed Mako-1.3.10 MarkupSafe-3.0.3 Pillow-11.0.0 PyMuPDF-1.26.5 PyYAML-6.0.3 SQLAlchemy-2.0.44 alembic-1.17.2 annotated-doc-0.0.4 annotated-types-0.7.0 anyio-4.11.0 argon2-cffi-23.1.0 argon2-cffi-bindings-25.1.0 attrs-26.1.0 bcrypt-5.0.0 certifi-2026.7.22 cffi-2.0.0 charset-normalizer-3.4.9 click-8.3.1 colorama-0.4.6 cryptography-46.0.3 deprecated-1.3.1 dnspython-2.8.0 ecdsa-0.19.1 email-validator-2.3.0 et-xmlfile-2.0.0 fastapi-0.121.2 greenlet-3.2.4 h11-0.16.0 httpcore-1.0.9 httptools-0.7.1 httpx-0.28.1 idna-3.11 iniconfig-2.3.0 msgpack-1.1.2 openpyxl-3.1.5 packaging-26.2 paho-mqtt-2.1.0 pdf2image-1.17.0 pdfrw-0.4 pluggy-1.6.0 psutil-7.2.2 psycopg2-binary-2.9.11 pyasn1-0.6.1 pycparser-2.23 pydantic-2.12.4 pydantic_core-2.41.5 pypdfium2-5.12.1 pytesseract-0.3.13 pytest-8.3.3 python-barcode-0.15.1 python-dateutil-2.9.0.post0 python-dotenv-1.2.1 python-jose-3.5.0 python-multipart-0.0.20 reportlab-4.4.4 requests-2.34.2 resend-2.34.0 rsa-4.9.1 six-1.17.0 sniffio-1.3.1 standardwebhooks-1.1.0 starlette-0.49.3 svix-1.98.0 typing-inspection-0.4.2 typing_extensions-4.15.0 tzdata-2025.2 urllib3-2.7.0 uvicorn-0.38.0 watchfiles-1.1.1 websockets-15.0.1 wrapt-2.3.0

```

### backend

```text
amodb/apps/technical_records/schemas.py:153
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:153: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class WatchlistRead(WatchlistCreate):

amodb/apps/technical_records/schemas.py:209
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:209: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ComplianceActionRead(ComplianceActionCreate):

amodb/apps/technical_records/schemas.py:223
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:223: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ProductionExecutionEvidenceRead(BaseModel):

amodb/apps/technical_records/schemas.py:247
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/technical_records/schemas.py:247: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class ProductionReleaseGateRead(BaseModel):

amodb/apps/maintenance_program/schemas.py:101
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/maintenance_program/schemas.py:101: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class MaintenanceProgramItemRead(MaintenanceProgramItemBase):

amodb/apps/maintenance_program/schemas.py:114
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/maintenance_program/schemas.py:114: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class MaintenanceProgramItemSummary(BaseModel):

amodb/apps/maintenance_program/schemas.py:203
  /home/runner/work/amo-portal/amo-portal/backend/amodb/apps/maintenance_program/schemas.py:203: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class AircraftProgramItemRead(AircraftProgramItemBase):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
2 passed, 87 warnings in 0.03s

```

### npm

```text

added 413 packages in 7s

```

### navigation

```text

> frontend@0.0.0 test:tenant-shell
> vitest run src/app/portalRouteManifest.test.ts src/services/departmentHome.test.ts && npm run check:css


[1m[46m RUN [49m[22m [36mv4.0.18 [39m[90m/home/runner/work/amo-portal/amo-portal/frontend[39m

 [32m✓[39m src/services/departmentHome.test.ts [2m([22m[2m2 tests[22m[2m)[22m[32m 8[2mms[22m[39m
 [32m✓[39m src/app/portalRouteManifest.test.ts [2m([22m[2m6 tests[22m[2m)[22m[32m 7[2mms[22m[39m

[2m Test Files [22m [1m[32m2 passed[39m[22m[90m (2)[39m
[2m      Tests [22m [1m[32m8 passed[39m[22m[90m (8)[39m
[2m   Start at [22m 10:44:39
[2m   Duration [22m 324ms[2m (transform 262ms, setup 0ms, import 338ms, tests 15ms, environment 0ms)[22m


> frontend@0.0.0 check:css
> node scripts/check-css-contract.mjs

CSS contract passed for 60 stylesheets.

```

### lint

```text
  404:5    error  Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/home/runner/work/amo-portal/amo-portal/frontend/src/portalRoutes.tsx:404:5
  402 |     !onboardingStatus.is_complete &&
  403 |     !isOnboardingRoute &&
> 404 |     !redirectedRef.current
      |     ^^^^^^^^^^^^^^^^^^^^^^ Cannot access ref value during render
  405 |   ) {
  406 |     redirectedRef.current = true;
  407 |     const amoCode = inferAmoCodeFromPath(location.pathname) || "system";                                                                                                                               react-hooks/refs
  404:6    error  Error: Cannot access refs during render

React refs are values that are not needed for rendering. Refs should only be accessed outside of render, such as in event handlers or effects. Accessing a ref value (the `current` property) during render can cause your component not to update as expected (https://react.dev/reference/react/useRef).

/home/runner/work/amo-portal/amo-portal/frontend/src/portalRoutes.tsx:404:6
  402 |     !onboardingStatus.is_complete &&
  403 |     !isOnboardingRoute &&
> 404 |     !redirectedRef.current
      |      ^^^^^^^^^^^^^^^^^^^^^ Cannot access ref value during render
  405 |   ) {
  406 |     redirectedRef.current = true;
  407 |     const amoCode = inferAmoCodeFromPath(location.pathname) || "system";

To initialize a ref only once, check that the ref is null with the pattern `if (ref.current == null) { ref.current = ... }`  react-hooks/refs
  464:7    error  'QualityRootRedirect' is assigned a value but never used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           @typescript-eslint/no-unused-vars

✖ 19 problems (19 errors, 0 warnings)


```

### build

```text

> frontend@0.0.0 build
> tsc -b && vite build

src/app/PortalRouteSurface.tsx(8,50): error TS2307: Cannot find module '../pages/ReliabilityReportsPage' or its corresponding type declarations.

```
