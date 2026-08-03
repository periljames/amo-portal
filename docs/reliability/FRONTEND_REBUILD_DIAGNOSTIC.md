# Transformed Reliability Frontend Diagnostic

- Run: `30807212501`
- Source SHA: `d8ab3cede97cef13062c37498235122d3d776516`
- UTC: `2026-08-03T10:52:39Z`

| Stage | Exit code |
|---|---:|
| Canonical replacement | 0 |
| Navigation/preload finalizer | 0 |
| Portal route surface patch | 0 |
| Frontend dependency install | 0 |
| Tenant navigation/CSS tests | 0 |
| Reliability-owned ESLint | 0 |
| Full production build | 0 |

### canonicalize

```text
Reliability now uses one canonical frontend and backend route surface.

```

### finalize

```text
Canonical Reliability navigation, preload and contract tests finalized.

```

### surface

```text
PortalRouteSurface now delegates every Reliability route to the canonical wildcard workspace.

```

### npm

```text

added 413 packages in 8s

```

### navigation

```text

> frontend@0.0.0 test:tenant-shell
> vitest run src/app/portalRouteManifest.test.ts src/services/departmentHome.test.ts && npm run check:css


[1m[46m RUN [49m[22m [36mv4.0.18 [39m[90m/home/runner/work/amo-portal/amo-portal/frontend[39m

 [32m✓[39m src/services/departmentHome.test.ts [2m([22m[2m2 tests[22m[2m)[22m[32m 8[2mms[22m[39m
 [32m✓[39m src/app/portalRouteManifest.test.ts [2m([22m[2m6 tests[22m[2m)[22m[32m 12[2mms[22m[39m

[2m Test Files [22m [1m[32m2 passed[39m[22m[90m (2)[39m
[2m      Tests [22m [1m[32m8 passed[39m[22m[90m (8)[39m
[2m   Start at [22m 10:51:56
[2m   Duration [22m 444ms[2m (transform 384ms, setup 0ms, import 447ms, tests 20ms, environment 0ms)[22m


> frontend@0.0.0 check:css
> node scripts/check-css-contract.mjs

CSS contract passed for 60 stylesheets.

```

### lint

```text

```

### build

```text
[2mdist/[22m[2massets/[22m[36mMyRosterWorkspace-DasL4lof.js                   [39m[1m[2m   18.54 kB[22m[1m[22m[2m │ gzip:   5.96 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformControlPage-CFpFZHY3.js                 [39m[1m[2m   19.05 kB[22m[1m[22m[2m │ gzip:   5.58 kB[22m
[2mdist/[22m[2massets/[22m[36mLoginPage-B6NBDWk0.js                           [39m[1m[2m   22.07 kB[22m[1m[22m[2m │ gzip:   8.60 kB[22m
[2mdist/[22m[2massets/[22m[36mindex--wKoBmYi.js                               [39m[1m[2m   22.21 kB[22m[1m[22m[2m │ gzip:   6.20 kB[22m
[2mdist/[22m[2massets/[22m[36mEmailServerSettingsPage-0yuy2kUt.js             [39m[1m[2m   22.30 kB[22m[1m[22m[2m │ gzip:   7.01 kB[22m
[2mdist/[22m[2massets/[22m[36mqms-B5HByC5M.js                                 [39m[1m[2m   22.45 kB[22m[1m[22m[2m │ gzip:   5.39 kB[22m
[2mdist/[22m[2massets/[22m[36mrosterUi-XrJG1zZf.js                            [39m[1m[2m   23.24 kB[22m[1m[22m[2m │ gzip:   7.00 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminUserDetailPage-CvEC3mH6.js                 [39m[1m[2m   23.95 kB[22m[1m[22m[2m │ gzip:   5.40 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditScheduleDetailPage-DQKSo3hO.js      [39m[1m[2m   24.58 kB[22m[1m[22m[2m │ gzip:   7.63 kB[22m
[2mdist/[22m[2massets/[22m[36mReliabilityWorkspacePage-BxT8dmBy.js            [39m[1m[2m   25.26 kB[22m[1m[22m[2m │ gzip:   6.84 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminDashboardPage-CnrvkXo3.js                  [39m[1m[2m   25.77 kB[22m[1m[22m[2m │ gzip:   7.25 kB[22m
[2mdist/[22m[2massets/[22m[36mindex-Czr2Gf7u.js                               [39m[1m[2m   26.77 kB[22m[1m[22m[2m │ gzip:   6.92 kB[22m
[2mdist/[22m[2massets/[22m[36mDashboardPage-BiIMIdQn.js                       [39m[1m[2m   28.09 kB[22m[1m[22m[2m │ gzip:   8.18 kB[22m
[2mdist/[22m[2massets/[22m[36musePlatformData-DTmdDDUv.js                     [39m[1m[2m   28.69 kB[22m[1m[22m[2m │ gzip:   8.82 kB[22m
[2mdist/[22m[2massets/[22m[36mPlanningProductionPages-Dkc2Sx_9.js             [39m[1m[2m   29.07 kB[22m[1m[22m[2m │ gzip:   6.38 kB[22m
[2mdist/[22m[2massets/[22m[36mCRSNewPage-DRSxCKRn.js                          [39m[1m[2m   29.11 kB[22m[1m[22m[2m │ gzip:  10.90 kB[22m
[2mdist/[22m[2massets/[22m[36mWorkforceHrWorkspace-C-NgsPh0.js                [39m[1m[2m   30.99 kB[22m[1m[22m[2m │ gzip:   7.61 kB[22m
[2mdist/[22m[2massets/[22m[36mPlatformIntegrationsPage-CStu0lx7.js            [39m[1m[2m   31.33 kB[22m[1m[22m[2m │ gzip:   8.18 kB[22m
[2mdist/[22m[2massets/[22m[36mUnifiedRosterPlanner-C7miwvGP.js                [39m[1m[2m   33.52 kB[22m[1m[22m[2m │ gzip:  10.81 kB[22m
[2mdist/[22m[2massets/[22m[36mRosteringSetupWorkspace-DvzLavMo.js             [39m[1m[2m   33.75 kB[22m[1m[22m[2m │ gzip:   9.19 kB[22m
[2mdist/[22m[2massets/[22m[36mSubscriptionManagementPage-BdyFvbVp.js          [39m[1m[2m   38.61 kB[22m[1m[22m[2m │ gzip:   9.52 kB[22m
[2mdist/[22m[2massets/[22m[36mDepartmentLayout-BuE76xFE.js                    [39m[1m[2m   40.19 kB[22m[1m[22m[2m │ gzip:  12.53 kB[22m
[2mdist/[22m[2massets/[22m[36mPublicCarInvitePage-CuqMGqIn.js                 [39m[1m[2m   40.33 kB[22m[1m[22m[2m │ gzip:  11.37 kB[22m
[2mdist/[22m[2massets/[22m[36mTechnicalRecordsPages-B3SBeqpe.js               [39m[1m[2m   42.43 kB[22m[1m[22m[2m │ gzip:   9.22 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsOverviewPage-CjGfAZtO.js                     [39m[1m[2m   44.26 kB[22m[1m[22m[2m │ gzip:  12.42 kB[22m
[2mdist/[22m[2massets/[22m[36mAdminAmoAssetsPage-CBA6zbqX.js                  [39m[1m[2m   46.49 kB[22m[1m[22m[2m │ gzip:  12.80 kB[22m
[2mdist/[22m[2massets/[22m[36mAircraftImportPage-Bt9Gd5w2.js                  [39m[1m[2m   48.31 kB[22m[1m[22m[2m │ gzip:  10.79 kB[22m
[2mdist/[22m[2massets/[22m[36mQMSTrainingUserPage-CNqkvG_a.js                 [39m[1m[2m   49.09 kB[22m[1m[22m[2m │ gzip:  12.69 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityCarsPage-B9X2cMAe.js                     [39m[1m[2m   53.14 kB[22m[1m[22m[2m │ gzip:  12.99 kB[22m
[2mdist/[22m[2massets/[22m[36mMyTrainingPage-FmNNXsxr.js                      [39m[1m[2m   55.37 kB[22m[1m[22m[2m │ gzip:  13.37 kB[22m
[2mdist/[22m[2massets/[22m[36mQmsCanonicalPage-C9mBWphy.js                    [39m[1m[2m   61.48 kB[22m[1m[22m[2m │ gzip:  17.59 kB[22m
[2mdist/[22m[2massets/[22m[36mManualReaderPage-BV3A8k9_.js                    [39m[1m[2m   62.51 kB[22m[1m[22m[2m │ gzip:  19.87 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditPlanSchedulePage-DWwL07AA.js        [39m[1m[2m   68.00 kB[22m[1m[22m[2m │ gzip:  16.42 kB[22m
[2mdist/[22m[2massets/[22m[36mQualityAuditRunHubPage-yMv-xFSe.js              [39m[1m[2m   84.50 kB[22m[1m[22m[2m │ gzip:  23.22 kB[22m
[2mdist/[22m[2massets/[22m[36mTrainingCompetencePage-B-YqtM73.js              [39m[1m[2m   87.37 kB[22m[1m[22m[2m │ gzip:  18.72 kB[22m
[2mdist/[22m[2massets/[22m[36mproxy-C4MhIOBP.js                               [39m[1m[2m  122.34 kB[22m[1m[22m[2m │ gzip:  40.37 kB[22m
[2mdist/[22m[2massets/[22m[36mdocx-preview-DExmN-Pl.js                        [39m[1m[2m  172.23 kB[22m[1m[22m[2m │ gzip:  50.40 kB[22m
[2mdist/[22m[2massets/[22m[36mDocControlPages-BKEHEkiG.js                     [39m[1m[2m  191.65 kB[22m[1m[22m[2m │ gzip:  42.73 kB[22m
[2mdist/[22m[2massets/[22m[36mmqtt.esm-sslCRx-_.js                            [39m[1m[2m  365.02 kB[22m[1m[22m[2m │ gzip: 110.45 kB[22m
[2mdist/[22m[2massets/[22m[36mgenerateCategoricalChart-DCtDYD9B.js            [39m[1m[2m  383.86 kB[22m[1m[22m[2m │ gzip: 105.91 kB[22m
[2mdist/[22m[2massets/[22m[36mEncoder-C1fvZ00O.js                             [39m[1m[2m  390.42 kB[22m[1m[22m[2m │ gzip: 102.86 kB[22m
[2mdist/[22m[2massets/[22m[36mpdf-vendor-pZBPlYZa.js                          [39m[1m[2m  422.68 kB[22m[1m[22m[2m │ gzip: 125.09 kB[22m
[2mdist/[22m[2massets/[22m[36mindex-DvRy4aMc.js                               [39m[1m[33m  509.23 kB[39m[22m[2m │ gzip: 142.37 kB[22m
[2mdist/[22m[2massets/[22m[36mgrid-vendor-CMBXYycc.js                         [39m[1m[33m  895.38 kB[39m[22m[2m │ gzip: 234.35 kB[22m
[33m
(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.[39m
[32m✓ built in 14.54s[39m

```
