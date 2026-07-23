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
])
