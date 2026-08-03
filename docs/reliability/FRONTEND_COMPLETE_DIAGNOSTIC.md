# Complete Reliability Frontend Diagnostic

- Run: `30813324178`
- Source: `ccf74c664fe4eabc9bb066da875b87a7f572145e`

| Stage | Exit |
|---|---:|
| service | 0 |
| workspace | 0 |
| sod | 0 |
| css | 0 |
| install | 0 |
| navigation | 0 |
| lint | 1 |
| build | 2 |
| contracts | 0 |

## service
```text
Canonical Reliability service client completed.
```

## workspace
```text
Complete Reliability workspace, routes and navigation wired.
```

## sod
```text
Independent Reliability approvals wired to the frontend.
```

## css
```text
Complete Reliability workflow styles appended.
```

## navigation
```text

> frontend@0.0.0 test:tenant-shell
> vitest run src/app/portalRouteManifest.test.ts src/services/departmentHome.test.ts && npm run check:css


[1m[46m RUN [49m[22m [36mv4.0.18 [39m[90m/home/runner/work/amo-portal/amo-portal/frontend[39m

 [32m✓[39m src/services/departmentHome.test.ts [2m([22m[2m2 tests[22m[2m)[22m[32m 7[2mms[22m[39m
 [32m✓[39m src/app/portalRouteManifest.test.ts [2m([22m[2m6 tests[22m[2m)[22m[32m 9[2mms[22m[39m

[2m Test Files [22m [1m[32m2 passed[39m[22m[90m (2)[39m
[2m      Tests [22m [1m[32m8 passed[39m[22m[90m (8)[39m
[2m   Start at [22m 12:23:02
[2m   Duration [22m 350ms[2m (transform 277ms, setup 0ms, import 349ms, tests 17ms, environment 0ms)[22m


> frontend@0.0.0 check:css
> node scripts/check-css-contract.mjs

CSS contract passed for 60 stylesheets.
```

## lint
```text

/home/runner/work/amo-portal/amo-portal/frontend/src/pages/reliability/ReliabilityWorkspacePage.tsx
  63:17  error  Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components  react-refresh/only-export-components

✖ 1 problem (1 error, 0 warnings)

```

## build
```text

> frontend@0.0.0 build
> tsc -b && vite build

src/pages/procurement/ProcurementModule.tsx(52,8): error TS2307: Cannot find module '../../services/procurement' or its corresponding type declarations.
src/pages/procurement/ProcurementModule.tsx(63,8): error TS2307: Cannot find module '../../types/procurement' or its corresponding type declarations.
src/pages/procurement/ProcurementModule.tsx(281,56): error TS7006: Parameter 'part' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(380,56): error TS7006: Parameter 'part' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(414,57): error TS7006: Parameter 'line' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(554,78): error TS7006: Parameter 'item' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(564,88): error TS7006: Parameter 'item' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(564,94): error TS7006: Parameter 'index' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(574,84): error TS7006: Parameter 'item' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(574,90): error TS7006: Parameter 'index' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(584,84): error TS7006: Parameter 'item' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(693,76): error TS7006: Parameter 'line' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(720,64): error TS7006: Parameter 'scope' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(786,301): error TS7006: Parameter 'part' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(793,284): error TS7006: Parameter 'location' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(803,284): error TS7006: Parameter 'vendor' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(803,318): error TS7006: Parameter 'vendor' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(851,298): error TS7006: Parameter 'part' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(861,283): error TS7006: Parameter 'location' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(866,305): error TS7006: Parameter 'line' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(879,346): error TS7006: Parameter 'location' implicitly has an 'any' type.
src/pages/procurement/ProcurementModule.tsx(880,339): error TS7006: Parameter 'location' implicitly has an 'any' type.
```

## contracts
```text
```
