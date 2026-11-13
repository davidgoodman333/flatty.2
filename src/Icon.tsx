export type IconName = "arrow" | "back" | "check" | "chevron" | "close" | "home" | "link" | "mail" | "map" | "search" | "shop" | "train" | "work";

export default function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    back: <path d="m15 18-6-6 6-6" />,
    check: <path d="m5 12 4 4L19 6" />,
    chevron: <path d="m8 10 4 4 4-4" />,
    close: <path d="M6 6l12 12M18 6 6 18" />,
    home: <path d="m3 11 9-8 9 8M5.5 9.5V21h13V9.5M9 21v-7h6v7" />,
    link: <path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.2 1.2M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.2-1.2" />,
    mail: <><rect x="3" y="5" width="18" height="14" rx="1" /><path d="m4 7 8 6 8-6" /></>,
    map: <><path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Z" /><path d="M9 3v15M15 6v15" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
    shop: <><path d="M4 10v10h16V10M3 10l2-6h14l2 6" /><path d="M3 10a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0M9 20v-5h6v5" /></>,
    train: <><rect x="5" y="3" width="14" height="15" rx="3" /><path d="M8 21l2-3M16 18l2 3M8 8h8M9 14h.01M15 14h.01" /></>,
    work: <><rect x="3" y="7" width="18" height="13" rx="1" /><path d="M9 7V4h6v3M3 12h18M10 12v2h4v-2" /></>,
  };

  return (
    <svg aria-hidden="true" fill="none" height={size} viewBox="0 0 24 24" width={size}>
      <g stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7">{paths[name]}</g>
    </svg>
  );
}
