# Eneco Heat — Finance Dashboard

Demo finance dashboard voor Eneco Warmte met dummy data.

## Features

- **Bruto marge brug** — waterfall met sprucing cost, heat loss revenues en bruto marge
- **Drill-down** — volledig doorklikbaar: portfolio → segment → profit center → klant → aansluiting
- **Interactieve kaart** — woningen en B2B-panden met omzet per aansluiting
- **Piekverlies analyse** — klanten waar effectieve kostprijs > tarief door piekverbruik
- **Vast vs. variabel** — omzet en kosten structuur
- **Revenue YTD backward** — werkelijk vs. modelmatig geschat (GJ volumes)
- **Sourcing** — P & Q op uurniveau per grid, gekoppeld aan invoices
- **Klanten & contracten** — volledig tarief- en componentoverzicht

## Starten

```bash
cd eneco-heat-dashboard
npm install
npm run dev
```

Open http://localhost:5173

## Tech stack

- React 19 + TypeScript
- Vite
- Tailwind CSS v4
- Recharts
- Lucide icons
