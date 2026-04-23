import { formatDistanceToNow } from "date-fns";
import { enUS as dateFnsEnUS, zhCN as dateFnsZhCN } from "date-fns/locale";

import { detectLocale, type Locale } from "@/core/i18n";
import { getLocaleFromCookie } from "@/core/i18n/cookies";

function getDateFnsLocale(locale: Locale) {
  switch (locale) {
    case "zh-CN":
      return dateFnsZhCN;
    case "en-US":
    default:
      return dateFnsEnUS;
  }
}

function toValidDate(date: Date | string | number | null | undefined): Date | null {
  if (date == null || date === "") return null;
  const dateObj = date instanceof Date ? date : new Date(date);
  if (isNaN(dateObj.getTime())) return null;
  return dateObj;
}

export function formatTimeAgo(date: Date | string | number, locale?: Locale) {
  const effectiveLocale =
    locale ??
    (getLocaleFromCookie() as Locale | null) ??
    // Fallback when cookie is missing (or on first render)
    detectLocale();

  // Validate date
  const dateObj = toValidDate(date);
  if (!dateObj) {
    return "-";
  }

  return formatDistanceToNow(dateObj, {
    addSuffix: true,
    locale: getDateFnsLocale(effectiveLocale),
  });
}

export function formatDateTime(date: Date | string | number | null | undefined): string {
  const dateObj = toValidDate(date);
  if (!dateObj) return "-";
  return dateObj.toLocaleString();
}

export function formatDate(date: Date | string | number | null | undefined): string {
  const dateObj = toValidDate(date);
  if (!dateObj) return "-";
  return dateObj.toLocaleDateString();
}
