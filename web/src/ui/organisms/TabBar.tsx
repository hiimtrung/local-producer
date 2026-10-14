// The app's bottom navigation: Lucent's floating glass tab bar with an icon and a label per section.
import { AppIcon, type AppIconName, Tabs } from "../atoms";

export interface TabItem<I extends string> {
  id: I;
  label: string;
  icon: AppIconName;
}

export interface TabBarProps<I extends string> {
  items: readonly TabItem<I>[];
  active: I;
  onSelect: (id: I) => void;
}

export function TabBar<I extends string>({ items, active, onSelect }: TabBarProps<I>) {
  return (
    <nav className="tab-bar" aria-label="Sections">
      <Tabs
        variant="bottom"
        aria-label="Sections"
        value={active}
        onChange={onSelect}
        tabs={items.map((t) => ({ id: t.id, label: t.label, icon: <AppIcon name={t.icon} size={22} /> }))}
      />
    </nav>
  );
}
