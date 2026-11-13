import {
  Bell,
  Briefcase,
  Building2,
  Calculator,
  FileText,
  FlaskConical,
  LayoutDashboard,
  LineChart,
  Settings,
  Shield,
  SlidersHorizontal,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  description: string;
  shortcut?: string;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export const navSections: NavSection[] = [
  {
    title: "Analyze",
    items: [
      {
        label: "Overview",
        to: "/",
        icon: LayoutDashboard,
        description: "Workspace overview, watchlists and market pulse",
        shortcut: "G O",
      },
      {
        label: "Companies",
        to: "/companies",
        icon: Building2,
        description: "Financial statements, ratios, filings and peers",
        shortcut: "G C",
      },
      {
        label: "Screener",
        to: "/screener",
        icon: SlidersHorizontal,
        description: "Screen the universe on fundamentals and technicals",
        shortcut: "G S",
      },
      {
        label: "Macro",
        to: "/macro",
        icon: LineChart,
        description: "Yields, inflation, growth, FX and commodities",
        shortcut: "G M",
      },
    ],
  },
  {
    title: "Workbench",
    items: [
      {
        label: "Valuation",
        to: "/valuation",
        icon: Calculator,
        description: "DCF, WACC, comps, scenarios and sensitivity",
        shortcut: "G V",
      },
      {
        label: "Portfolios",
        to: "/portfolios",
        icon: Briefcase,
        description: "Holdings, performance, risk and optimisation",
        shortcut: "G P",
      },
      {
        label: "Backtest Lab",
        to: "/backtest",
        icon: FlaskConical,
        description: "Design, test and stress systematic strategies",
        shortcut: "G B",
      },
      {
        label: "Research",
        to: "/research",
        icon: Sparkles,
        description: "Ask questions across filings, news and documents",
        shortcut: "G R",
      },
    ],
  },
  {
    title: "Library",
    items: [
      {
        label: "Reports",
        to: "/reports",
        icon: FileText,
        description: "Tear sheets, portfolio reviews and exports",
      },
      {
        label: "Alerts",
        to: "/alerts",
        icon: Bell,
        description: "Price, ratio, sentiment and filing alerts",
      },
    ],
  },
  {
    title: "Administration",
    items: [
      {
        label: "Team & access",
        to: "/admin",
        icon: Shield,
        description: "Users, roles, audit log and data providers",
      },
      {
        label: "Settings",
        to: "/settings",
        icon: Settings,
        description: "Profile, security, API keys and preferences",
      },
    ],
  },
];

export const allNavItems = navSections.flatMap((section) => section.items);

export function findNavItem(pathname: string): NavItem | undefined {
  return allNavItems.find((item) => item.to !== "/" && pathname.startsWith(item.to));
}
