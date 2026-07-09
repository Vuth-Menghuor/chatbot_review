import { h } from 'vue';
import type { Component } from 'vue';
import type { IconSet, IconProps } from 'vuetify';
import * as LucideIcons from 'lucide-vue-next';

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.hook('vuetify:configuration', ({ vuetifyOptions }) => {
    const aliases: Record<string, string> = {
      'close-circle': 'XCircle',
      checkboxIndeterminate: 'SquareMinus',
      checkboxOff: 'Square',
      checkboxOn: 'SquareCheck',
      paperclip: 'Paperclip',
      radioOff: 'Circle',
      radioOn: 'CircleDot',
      send: 'Send',
      delete: 'Trash2',
      plus: 'Plus',
      'chevron-down': 'ChevronDown',
      'chevron-up': 'ChevronUp',
      menu: 'Menu',
    };

    const lucideSet: IconSet = {
      component: (props: IconProps) => {
        let name = typeof props.icon === 'string' ? props.icon : '';

        // Remove prefixes
        name = name.replace(/^(lucide-|mdi-)/, '');
        name = name.replace(/^\$/, '');

        // Check manual aliases first
        const aliasMatch = aliases[name];
        if (aliasMatch) {
          name = aliasMatch;
        } else {
          // Fallback to PascalCase conversion
          name = name
            .split('-')
            .map((str) => str.charAt(0).toUpperCase() + str.slice(1))
            .join('');
        }

        const iconRegistry = LucideIcons as Record<string, Component | undefined>;
        const LucideIcon = iconRegistry[name];
        if (!LucideIcon) {
          // Final fallback to X as a generic warning icon if not found
          const WarningIcon = iconRegistry.AlertCircle;
          if (WarningIcon) {
            return h(WarningIcon, {
              class: ['lucide', props.class],
            });
          }

          return h('span', null, String(props.icon));
        }
        return h(LucideIcon, {
          class: ['lucide', props.class],
        });
      },
    };

    vuetifyOptions.icons = {
      defaultSet: 'lucide',
      sets: {
        lucide: lucideSet,
      },
    };
  });
});
