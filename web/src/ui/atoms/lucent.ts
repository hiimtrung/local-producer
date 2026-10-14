// Typed bindings for the Lucent design system (web/vendor/lucent/bundle.js, pinned in VENDOR.json). The bundle is a
// plain script that reads window.React and fills window.Lucent; it is bundled into app.js after React is published
// on window. These are the atoms of the UI: everything else is composed from them. The prop types below describe
// what bundle.js actually reads; extend them here when a page needs another prop.
import type {
  ButtonHTMLAttributes,
  ChangeEvent,
  InputHTMLAttributes,
  ReactElement,
  ReactNode,
  TextareaHTMLAttributes,
} from "react";
import "./react-global";
import "../../../vendor/lucent/bundle.js";

export type Tone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";
export type Size = "sm" | "md" | "lg";
export type IconName =
  | "search" | "close" | "close-circle" | "chevron-down" | "chevron-right" | "chevron-left" | "chevron-updown"
  | "check" | "minus" | "plus" | "info" | "check-circle" | "warning" | "error" | "home" | "person" | "gear" | "bell"
  | "heart" | "share" | "trash" | "pin" | "wifi" | "moon"; // prettier-ignore
/** A Lucent icon name or any rendered node (e.g. an AppIcon). */
export type IconSpec = IconName | ReactNode;
export type OptionValue = string | number;

export interface Option<V extends OptionValue = string> {
  value: V;
  label: string;
  description?: string | null;
  disabled?: boolean;
  icon?: IconSpec;
}

interface FieldProps {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  className?: string;
  id?: string;
}

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  variant?: "glass" | "prominent" | "plain" | "destructive";
  size?: Size;
  icon?: IconSpec;
  iconEnd?: IconSpec;
  block?: boolean;
  loading?: boolean;
  children?: ReactNode;
}

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  icon: IconSpec;
  label: string;
  variant?: "glass" | "prominent" | "plain";
  size?: Size;
}

export interface TextFieldProps
  extends FieldProps,
    Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "defaultValue" | "onChange" | "size"> {
  value?: string;
  defaultValue?: string;
  onChange?: (value: string, event?: ChangeEvent<HTMLInputElement>) => void;
  size?: Size;
  leading?: IconSpec;
  trailing?: ReactNode;
  clearable?: boolean;
}

export interface TextAreaProps
  extends FieldProps,
    Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "defaultValue" | "onChange"> {
  value?: string;
  defaultValue?: string;
  onChange?: (value: string, event: ChangeEvent<HTMLTextAreaElement>) => void;
  autoGrow?: boolean;
  maxRows?: number;
}

export interface SelectProps<V extends OptionValue> extends FieldProps {
  options: readonly Option<V>[];
  value?: V;
  defaultValue?: V;
  onChange?: (value: V, option: Option<V>) => void;
  placeholder?: string;
  size?: Size;
  disabled?: boolean;
  name?: string;
  "aria-label"?: string;
}

export interface SegmentedControlProps<V extends OptionValue> {
  options: readonly Option<V>[];
  value?: V;
  defaultValue?: V;
  onChange?: (value: V, option: Option<V>) => void;
  size?: "sm" | "md";
  label?: string;
  "aria-label"?: string;
  className?: string;
}

export interface SwitchProps {
  checked?: boolean;
  defaultChecked?: boolean;
  onChange?: (checked: boolean) => void;
  label?: ReactNode;
  disabled?: boolean;
  id?: string;
  className?: string;
  "aria-label"?: string;
}

export interface SliderProps {
  value?: number;
  defaultValue?: number;
  onChange?: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  label?: ReactNode;
  showValue?: boolean;
  format?: (value: number) => string;
  disabled?: boolean;
  id?: string;
  className?: string;
  "aria-label"?: string;
}

export interface Tab<I extends string> {
  id: I;
  label: ReactNode;
  icon?: IconSpec;
  content?: ReactNode;
}

export interface TabsProps<I extends string> {
  tabs: readonly Tab<I>[];
  value?: I;
  defaultValue?: I;
  onChange?: (id: I) => void;
  variant?: "top" | "bottom";
  id?: string;
  className?: string;
  "aria-label"?: string;
}

export interface CardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  footer?: ReactNode;
  variant?: "regular" | "thick" | "clear" | "tinted";
  className?: string;
  children?: ReactNode;
}

export interface ListProps {
  header?: ReactNode;
  className?: string;
  children?: ReactNode;
}

export interface ListItemProps {
  title: ReactNode;
  subtitle?: ReactNode;
  detail?: ReactNode;
  trailing?: ReactNode;
  leading?: ReactNode;
  icon?: IconSpec;
  iconColor?: string;
  chevron?: boolean;
  href?: string;
  onClick?: () => void;
}

export interface BadgeProps {
  tone?: Tone;
  /** true = the tone's own icon */
  icon?: boolean | IconSpec;
  className?: string;
  children?: ReactNode;
}

export interface ProgressProps {
  value?: number | undefined;
  max?: number;
  indeterminate?: boolean;
  label?: string;
  showValue?: boolean;
  className?: string;
}

export interface ToastProps {
  tone?: "info" | "success" | "warning" | "danger";
  title: ReactNode;
  message?: ReactNode;
  action?: ReactNode;
  onClose?: () => void;
  className?: string;
}

export interface DialogProps {
  open: boolean;
  title: ReactNode;
  onClose?: () => void;
  actions?: ReactNode;
  dismissible?: boolean;
  autoFocus?: boolean;
  inline?: boolean;
  role?: "dialog" | "alertdialog";
  children?: ReactNode;
}

export interface SpinnerProps {
  size?: "md" | "lg";
  label?: string;
}

export interface IconProps {
  name: IconName;
  size?: number;
  strokeWidth?: number;
  label?: string;
  className?: string;
}

type Component<P> = (props: P) => ReactElement | null;

interface LucentNamespace {
  Button: Component<ButtonProps>;
  IconButton: Component<IconButtonProps>;
  TextField: Component<TextFieldProps>;
  TextArea: Component<TextAreaProps>;
  Select: <V extends OptionValue>(props: SelectProps<V>) => ReactElement | null;
  SegmentedControl: <V extends OptionValue>(props: SegmentedControlProps<V>) => ReactElement | null;
  Switch: Component<SwitchProps>;
  Slider: Component<SliderProps>;
  Tabs: <I extends string>(props: TabsProps<I>) => ReactElement | null;
  Card: Component<CardProps>;
  List: Component<ListProps>;
  ListItem: Component<ListItemProps>;
  Badge: Component<BadgeProps>;
  Progress: Component<ProgressProps>;
  Toast: Component<ToastProps>;
  Dialog: Component<DialogProps>;
  Spinner: Component<SpinnerProps>;
  Icon: Component<IconProps>;
}

declare global {
  interface Window {
    Lucent: LucentNamespace;
  }
}

const L = window.Lucent;
export const {
  Badge,
  Button,
  Card,
  Dialog,
  Icon,
  IconButton,
  List,
  ListItem,
  Progress,
  SegmentedControl,
  Select,
  Slider,
  Spinner,
  Switch,
  Tabs,
  TextArea,
  TextField,
  Toast,
} = L;
