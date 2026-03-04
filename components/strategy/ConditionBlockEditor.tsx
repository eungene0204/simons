"use client";

import { useState, useEffect } from "react";
import { X, CheckCircle } from "phosphor-react";
import { Condition } from "@/types/strategy";
import { signalBlocks } from "@/lib/strategy-blocks";

interface ConditionBlockEditorProps {
  condition: Condition;
  onSave: (condition: Condition) => void;
  onCancel: () => void;
}

export default function ConditionBlockEditor({
  condition,
  onSave,
  onCancel,
}: ConditionBlockEditorProps) {
  const [params, setParams] = useState(condition.params);
  const [weight, setWeight] = useState(condition.weight || 1);
  const block = signalBlocks[condition.id];

  useEffect(() => {
    setParams(condition.params);
    setWeight(condition.weight || 1);
  }, [condition]);

  const handleParamChange = (key: string, value: any) => {
    setParams({ ...params, [key]: value });
  };

  const handleSave = () => {
    onSave({
      ...condition,
      params,
      weight,
    });
  };

  if (!block) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-[#1a1a1a] rounded-lg border border-gray-800 w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-800">
          <div>
            <h3 className="text-lg font-semibold text-white">{block.name}</h3>
            <p className="text-sm text-gray-400 mt-1">{block.description}</p>
          </div>
          <button
            onClick={onCancel}
            className="text-gray-400 hover:text-white"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Parameters */}
        <div className="p-4 space-y-4">
          {Object.entries(block.paramSchema).map(([key, schema]) => {
            const currentValue = params[key] !== undefined ? params[key] : block.defaultParams[key];

            return (
              <div key={key}>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {schema.label}
                  {schema.tooltip && (
                    <span className="ml-2 text-xs text-gray-500">
                      ({schema.tooltip})
                    </span>
                  )}
                </label>

                {schema.type === "number" && (
                  <div className="space-y-2">
                    <input
                      type="number"
                      min={schema.min}
                      max={schema.max}
                      step={schema.step || 1}
                      value={currentValue}
                      onChange={(e) =>
                        handleParamChange(key, parseFloat(e.target.value))
                      }
                      className="w-full px-3 py-2 bg-[#151515] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                    />
                    <div className="flex justify-between text-xs text-gray-500">
                      <span>Min: {schema.min}</span>
                      <span>Max: {schema.max}</span>
                    </div>
                  </div>
                )}

                {schema.type === "select" && (
                  <select
                    value={currentValue}
                    onChange={(e) => handleParamChange(key, e.target.value)}
                    className="w-full px-3 py-2 bg-[#151515] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  >
                    {schema.options?.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                )}

                {schema.type === "boolean" && (
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={currentValue || false}
                      onChange={(e) => handleParamChange(key, e.target.checked)}
                      className="w-4 h-4 text-blue-500 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <span className="text-sm text-gray-300">활성화</span>
                  </label>
                )}
              </div>
            );
          })}

          {/* Weight for weighted sum */}
          {condition.type === "indicator" || condition.type === "flow" ? (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                가중치 (Weighted Sum 사용 시)
              </label>
              <input
                type="number"
                min={0}
                max={10}
                step={0.1}
                value={weight}
                onChange={(e) => setWeight(parseFloat(e.target.value))}
                className="w-full px-3 py-2 bg-[#151515] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 p-4 border-t border-gray-800">
          <button
            onClick={onCancel}
            className="px-4 py-2 bg-gray-700 text-white rounded-lg text-sm font-medium hover:bg-gray-600"
          >
            취소
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-600 flex items-center gap-2"
          >
            <CheckCircle className="w-5 h-5" />
            저장
          </button>
        </div>
      </div>
    </div>
  );
}

