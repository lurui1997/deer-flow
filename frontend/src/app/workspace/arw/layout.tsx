import { Metadata } from "next";

export const metadata: Metadata = {
  title: "Agent Runtime Worker | DeerFlow",
  description: "Monitor and manage Agent Runtime Worker instances",
};

export default function ARWLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="h-full">
      {children}
    </div>
  );
}
