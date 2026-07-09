export interface SettingsSwitchListItem {
  key: string;
  title: string;
  description: string;
  learnMoreUrl?: string;
  learnMoreLabel?: string;
  modelValue: boolean;
  onUpdate: (value: boolean) => void;
}
