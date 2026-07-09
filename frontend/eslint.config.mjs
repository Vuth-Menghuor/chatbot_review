import withNuxt from './.nuxt/eslint.config.mjs';
import eslintConfigPrettier from 'eslint-config-prettier';

const baseComponentMessage =
  'Use components from app/components/base (BaseButton, BaseIconButton, BaseActionRow, BaseMenuList, etc.).';

export default withNuxt([
  {
    rules: {
      'vue/multi-word-component-names': 'off',
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/unified-signatures': 'warn',
      '@typescript-eslint/no-unused-vars': 'warn',
      'vue/no-mutating-props': 'warn',
      'no-case-declarations': 'warn',
    },
  },
  {
    files: ['app/components/**/*.vue'],
    ignores: ['app/components/base/**', 'app/components/renderers/**'],
    rules: {
      'vue/no-restricted-html-elements': [
        'warn',
        {
          element: 'button',
          message: baseComponentMessage,
        },
        {
          element: 'v-btn',
          message: baseComponentMessage,
        },
        {
          element: 'v-list-item',
          message: baseComponentMessage,
        },
      ],
    },
  },
  eslintConfigPrettier,
]);
