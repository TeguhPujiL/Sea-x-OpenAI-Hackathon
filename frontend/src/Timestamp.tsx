import React from "react";

export function Timestamp({ value }: { value: string }) {
  const label = new Intl.DateTimeFormat("en-GB", {
    year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", timeZoneName: "short",
  }).format(new Date(value));
  return <time dateTime={value} title={value}>{label}</time>;
}
