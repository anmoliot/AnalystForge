import React from "react";

export interface RatioEntry {
  key: string;
  label: string;
  value: number | string;
  unit?: string;
  formula?: string;
  note?: string;
}

export interface RatiosTableProps {
  ratios: RatioEntry[];
}

const RatiosTable: React.FC<RatiosTableProps> = ({ ratios }) => {
  return (
    <div className="overflow-x-auto" data-test="ratios-table">
      <table className="min-w-full border border-gray-200">
        <thead className="bg-gray-100">
          <tr>
            <th className="px-4 py-2 text-left">Metric</th>
            <th className="px-4 py-2 text-left">Value</th>
            <th className="px-4 py-2 text-left">Unit</th>
            <th className="px-4 py-2 text-left">Formula</th>
            <th className="px-4 py-2 text-left">Note</th>
          </tr>
        </thead>
        <tbody>
          {ratios.map((r) => (
            <tr key={r.key} className="border-t border-gray-200">
              <td className="px-4 py-2">{r.label}</td>
              <td className="px-4 py-2">{r.value}</td>
              <td className="px-4 py-2">{r.unit ?? ""}</td>
              <td className="px-4 py-2">{r.formula ?? ""}</td>
              <td className="px-4 py-2">{r.note ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default RatiosTable;
