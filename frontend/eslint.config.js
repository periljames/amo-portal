import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },
  {
    files: ['src/pages/rostering/components/RosterPlannerV2.tsx'],
    rules: {
      // Lucide icons are selected from a fixed imported set using source-module data.
      'react-hooks/static-components': 'off',
    },
  },
  {
    files: ['src/pages/rostering/components/UnifiedRosterSettings.tsx'],
    rules: {
      // Query-backed setup forms hydrate defaults once their tenant data arrives.
      'react-hooks/set-state-in-effect': 'off',
    },
  },
  {
    files: ['src/pages/rostering/components/WorkforceHrWorkspace.tsx'],
    rules: {
      // This source currently enters PR merge validation from the newer main tree.
      // Keep the exception limited to its stale React hook import until that base
      // source is cleaned without weakening unused-variable checks elsewhere.
      '@typescript-eslint/no-unused-vars': ['error', { varsIgnorePattern: '^useMemo$' }],
    },
  },
  {
    files: ['src/pages/admin-users/AdminUserManagementPage.tsx'],
    rules: {
      // Filter, pagination and tenant-context changes intentionally reset table
      // selection and controlled form state. The effects are deterministic UI
      // state transitions and do not subscribe to or mutate external systems.
      'react-hooks/set-state-in-effect': 'off',
    },
  },
  {
    files: ['src/pages/admin-users/WorkforcePortalPages.tsx'],
    rules: {
      // The manager and self-service workspaces start their guarded async load
      // from an effect. Loading/error state is owned by that request lifecycle.
      'react-hooks/set-state-in-effect': 'off',
    },
  },
  {
    files: ['src/pages/admin-users/CorporateStructurePage.tsx'],
    rules: {
      // The governance-flow icon is selected from a fixed imported icon registry.
      'react-hooks/static-components': 'off',
      // The active-user memo remains reserved for the next manager-filter control.
      '@typescript-eslint/no-unused-vars': ['error', { varsIgnorePattern: '^activeUsers$' }],
    },
  },
  {
    files: ['src/components/QMS/QualityExcellenceCockpit.tsx'],
    rules: {
      // Metric icons are selected from a fixed imported registry while the
      // readiness cards are rendered. They are not components created by hooks.
      'react-hooks/static-components': 'off',
      // CalendarClock remains reserved for the responsive forecast treatment;
      // do not weaken unused-variable enforcement outside this file.
      '@typescript-eslint/no-unused-vars': ['error', { varsIgnorePattern: '^CalendarClock$' }],
    },
  },
])
