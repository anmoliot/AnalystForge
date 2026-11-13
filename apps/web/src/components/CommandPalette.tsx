import { ArrowRight, Command, ExternalLink, Moon, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";

import { allNavItems } from "@/config/nav";
import { useCommandPalette } from "@/stores/commandPalette";
import { useTheme } from "@/stores/theme";

interface PaletteAction {
  id: string;
  label: string;
  hint: string;
  icon: typeof Search;
  run: () => void;
  keywords?: string;
}

export function CommandPalette() {
  const open = useCommandPalette((state) => state.open);
  const setOpen = useCommandPalette((state) => state.setOpen);
  const navigate = useNavigate();
  const toggleTheme = useTheme((state) => state.toggle);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  const actions = useMemo<PaletteAction[]>(() => {
    const navActions = allNavItems.map((item) => ({
      id: `nav:${item.to}`,
      label: item.label,
      hint: item.description,
      icon: item.icon,
      keywords: `${item.label} ${item.description}`.toLowerCase(),
      run: () => {
        navigate(item.to);
        setOpen(false);
      },
    }));
    return [
      ...navActions,
      {
        id: "action:theme",
        label: "Toggle colour theme",
        hint: "Switch between dark and light",
        icon: Moon,
        keywords: "theme dark light appearance",
        run: () => {
          toggleTheme();
          setOpen(false);
        },
      },
      {
        id: "action:docs",
        label: "Open API documentation",
        hint: "Interactive OpenAPI reference",
        icon: ExternalLink,
        keywords: "api docs openapi swagger",
        run: () => {
          window.open("/docs", "_blank", "noopener,noreferrer");
          setOpen(false);
        },
      },
    ];
  }, [navigate, setOpen, toggleTheme]);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return actions;
    return actions.filter(
      (action) =>
        action.keywords?.includes(term) ||
        action.label.toLowerCase().includes(term) ||
        action.hint.toLowerCase().includes(term),
    );
  }, [actions, query]);

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(!open);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, setOpen]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  if (!open) return null;

  const onDialogKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (filtered.length === 0 ? 0 : (index + 1) % filtered.length));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) =>
        filtered.length === 0 ? 0 : (index - 1 + filtered.length) % filtered.length,
      );
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      filtered[activeIndex]?.run();
      return;
    }
    if (event.key === "Tab" && dialogRef.current) {
      const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input, [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (!first || !last) return;
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 px-4 pt-[12vh] backdrop-blur-[2px]"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) setOpen(false);
      }}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onKeyDown={onDialogKeyDown}
        className="w-full max-w-xl overflow-hidden rounded-lg border border-line bg-panel shadow-2xl animate-slide-up"
      >
        <div className="flex h-11 items-center gap-2 border-b border-line px-3">
          <Search className="size-4 text-muted" aria-hidden="true" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search pages, symbols and actions…"
            aria-label="Search commands"
            aria-controls="command-results"
            aria-activedescendant={filtered[activeIndex]?.id}
            className="h-full flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-muted/70"
          />
          <span className="kbd">ESC</span>
        </div>
        <ul id="command-results" role="listbox" className="max-h-[340px] overflow-y-auto p-1.5">
          {filtered.length === 0 ? (
            <li className="px-3 py-8 text-center text-xs text-muted">
              No commands match “{query}”.
            </li>
          ) : (
            filtered.map((action, index) => {
              const Icon = action.icon;
              return (
                <li key={action.id} role="option" aria-selected={index === activeIndex}>
                  <button
                    type="button"
                    id={action.id}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={action.run}
                    className={`flex w-full items-center gap-3 rounded px-2.5 py-2 text-left transition-colors ${
                      index === activeIndex ? "bg-elevated text-ink" : "text-muted"
                    }`}
                  >
                    <Icon className="size-4 shrink-0" aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm">{action.label}</span>
                      <span className="block truncate text-2xs text-muted">{action.hint}</span>
                    </span>
                    <ArrowRight
                      className={`size-3.5 ${index === activeIndex ? "opacity-100" : "opacity-0"}`}
                      aria-hidden="true"
                    />
                  </button>
                </li>
              );
            })
          )}
        </ul>
        <div className="flex items-center justify-between border-t border-line px-3 py-1.5 text-2xs text-muted">
          <span className="flex items-center gap-1">
            <Command className="size-3" aria-hidden="true" />K to open
          </span>
          <span className="flex items-center gap-2">
            <span>↑↓ navigate</span>
            <span>↵ select</span>
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
