"use client";

import { useEffect, useState, useLayoutEffect, useMemo, memo } from "react";
import { useRouter } from "next/navigation";
import {
  StarIcon,
  MagnifyingGlassIcon,
  FolderIcon,
  PlusIcon,
  PencilIcon,
  PencilSquareIcon,
  TrashIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  XMarkIcon,
  Bars3Icon,
  ArrowsUpDownIcon,
} from "@heroicons/react/24/outline";
import { StarIcon as StarIconSolid } from "@heroicons/react/24/solid";
import StockSearchModal from "@/components/stock/StockSearchModal";
import {
  getWatchlistSymbols,
  addMultipleToWatchlist,
  removeFromWatchlist,
  getWatchlistGroups,
  createWatchlistGroup,
  updateWatchlistGroup,
  deleteWatchlistGroup,
  assignSymbolToGroup,
  type WatchlistGroup,
} from "@/lib/watchlist";

interface WatchlistItem {
  symbol: string;
  name: string;
  logo?: string;
  currentPrice: number;
  changePercent: number;
  change: number;
  volume: number;
  groupId?: string;
}

interface WatchlistDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onStockSelect?: (symbol: string, name: string) => void;
}

function WatchlistDrawer({
  isOpen,
  onClose,
  onStockSelect,
}: WatchlistDrawerProps) {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [headerHeight, setHeaderHeight] = useState(76);
  const [groups, setGroups] = useState<WatchlistGroup[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [isGroupModalOpen, setIsGroupModalOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<WatchlistGroup | null>(null);
  const [groupName, setGroupName] = useState("");
  const [groupColor, setGroupColor] = useState("#3B82F6");
  const [isGroupDropdownOpen, setIsGroupDropdownOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [selectedGroupForEdit, setSelectedGroupForEdit] = useState<
    string | null
  >(null);
  const [selectedItemsForEdit, setSelectedItemsForEdit] = useState<Set<string>>(
    new Set()
  );
  const router = useRouter();

  const fetchWatchlist = async (isInitial = false) => {
    try {
      if (isInitial) {
        setLoading(true);
      }

      // Get symbols from localStorage
      const watchlistSymbols = getWatchlistSymbols();
      const symbols = watchlistSymbols.map((item) => item.symbol);

      // If no symbols in localStorage, use empty array (will show default mock data)
      const symbolsParam = symbols.length > 0 ? JSON.stringify(symbols) : null;
      const url = symbolsParam
        ? `/api/watchlist?symbols=${encodeURIComponent(symbolsParam)}`
        : "/api/watchlist";

      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        // Create a map of API results by symbol for quick lookup
        const apiItemsMap = new Map(
          (data.items || []).map((item: WatchlistItem) => [item.symbol, item])
        );

        // Map groupId from localStorage to items, maintaining localStorage order
        const itemsWithGroups: WatchlistItem[] = watchlistSymbols
          .map((symbolData) => {
            const apiItem = apiItemsMap.get(symbolData.symbol);
            if (!apiItem) return null;
            return { ...apiItem, groupId: symbolData.groupId };
          })
          .filter((item) => item !== null) as WatchlistItem[];

        setItems(itemsWithGroups);
      }
    } catch (error) {
      console.error("Failed to fetch watchlist:", error);
    } finally {
      if (isInitial) {
        setLoading(false);
      }
    }
  };

  const handleAddToWatchlist = async (
    itemsToAdd: Array<{ symbol: string; name: string }>
  ) => {
    // First, add items to watchlist
    const addedCount = addMultipleToWatchlist(itemsToAdd);

    if (addedCount > 0) {
      // Get all groups
      const allGroups = getWatchlistGroups();

      // Assign each added item to the selected group or first group
      const targetGroupId =
        selectedGroupId || (allGroups.length > 0 ? allGroups[0].id : undefined);

      itemsToAdd.forEach((item) => {
        if (targetGroupId) {
          assignSymbolToGroup(item.symbol, targetGroupId);
        }
      });

      // Refresh the watchlist to show new items
      await fetchWatchlist(false);

      setIsSearchOpen(false);
    }
  };

  const loadGroups = () => {
    const loadedGroups = getWatchlistGroups();
    setGroups(loadedGroups);
  };

  const handleCreateGroup = () => {
    if (!groupName.trim()) return;

    try {
      const newGroup = createWatchlistGroup(groupName.trim(), groupColor);
      loadGroups();
      setGroupName("");
      setGroupColor("#3B82F6");
      setIsGroupModalOpen(false);
    } catch (error) {
      console.error("Failed to create group:", error);
    }
  };

  const handleUpdateGroup = () => {
    if (!editingGroup || !groupName.trim()) return;

    try {
      updateWatchlistGroup(editingGroup.id, {
        name: groupName.trim(),
        color: groupColor,
      });
      loadGroups();
      setEditingGroup(null);
      setGroupName("");
      setGroupColor("#3B82F6");
      setIsGroupModalOpen(false);
      fetchWatchlist(false);
    } catch (error) {
      console.error("Failed to update group:", error);
    }
  };

  const handleDeleteGroup = (groupId: string) => {
    if (
      confirm(
        "그룹을 삭제하시겠습니까? 그룹에 속한 종목들은 그룹이 해제됩니다."
      )
    ) {
      try {
        deleteWatchlistGroup(groupId);
        loadGroups();
        if (selectedGroupId === groupId) {
          setSelectedGroupId(null);
        }
        fetchWatchlist(false);
      } catch (error) {
        console.error("Failed to delete group:", error);
      }
    }
  };

  const handleAssignToGroup = (symbol: string, groupId: string | undefined) => {
    try {
      assignSymbolToGroup(symbol, groupId);
      fetchWatchlist(false);
    } catch (error) {
      console.error("Failed to assign to group:", error);
    }
  };

  const openEditGroupModal = (group: WatchlistGroup) => {
    setEditingGroup(group);
    setGroupName(group.name);
    setGroupColor(group.color || "#3B82F6");
    setIsGroupModalOpen(true);
  };

  const openCreateGroupModal = () => {
    setEditingGroup(null);
    setGroupName("");
    setGroupColor("#3B82F6");
    setIsGroupModalOpen(true);
  };

  const closeGroupModal = () => {
    setIsGroupModalOpen(false);
    setEditingGroup(null);
    setGroupName("");
    setGroupColor("#3B82F6");
  };

  const filteredItems = useMemo(() => {
    if (selectedGroupId === null) {
      // Show all items when no group is selected
      return items;
    }
    return items.filter((item) => item.groupId === selectedGroupId);
  }, [items, selectedGroupId]);

  const handleRemoveUngroupedItems = () => {
    if (confirm("그룹에 포함되지 않은 종목들을 모두 삭제하시겠습니까?")) {
      const ungroupedItems = items.filter(
        (item) =>
          !item.groupId || item.groupId === null || item.groupId === undefined
      );

      ungroupedItems.forEach((item) => {
        removeFromWatchlist(item.symbol);
      });

      fetchWatchlist(false);
    }
  };

  const handleOpenEditModal = () => {
    setIsEditModalOpen(true);
    loadGroups();
    if (groups.length > 0 && !selectedGroupForEdit) {
      setSelectedGroupForEdit(groups[0].id);
    }
    setSelectedItemsForEdit(new Set());
  };

  const handleCloseEditModal = () => {
    setIsEditModalOpen(false);
    setSelectedGroupForEdit(null);
    setSelectedItemsForEdit(new Set());
  };

  const handleToggleItemSelection = (symbol: string) => {
    const newSelected = new Set(selectedItemsForEdit);
    if (newSelected.has(symbol)) {
      newSelected.delete(symbol);
    } else {
      newSelected.add(symbol);
    }
    setSelectedItemsForEdit(newSelected);
  };

  const handleMoveSelectedItems = (targetGroupId: string | null) => {
    if (selectedItemsForEdit.size === 0) return;
    selectedItemsForEdit.forEach((symbol) => {
      assignSymbolToGroup(symbol, targetGroupId || undefined);
    });
    setSelectedItemsForEdit(new Set());
    fetchWatchlist(false);
  };

  const handleDeleteSelectedItems = () => {
    if (selectedItemsForEdit.size === 0) return;
    if (
      confirm(`선택한 ${selectedItemsForEdit.size}개 종목을 삭제하시겠습니까?`)
    ) {
      selectedItemsForEdit.forEach((symbol) => {
        removeFromWatchlist(symbol);
      });
      setSelectedItemsForEdit(new Set());
      fetchWatchlist(false);
    }
  };

  const getGroupItemCount = (groupId: string | null) => {
    if (groupId === null) {
      return items.filter((item) => !item.groupId).length;
    }
    return items.filter((item) => item.groupId === groupId).length;
  };

  const getItemsInGroup = (groupId: string | null) => {
    if (groupId === null) {
      return items.filter((item) => !item.groupId);
    }
    return items.filter((item) => item.groupId === groupId);
  };

  // CSS Custom Property에서 높이 읽기 (최신 CSS 변수 활용)
  useEffect(() => {
    if (isOpen) {
      const updateHeightFromCSS = () => {
        const height = getComputedStyle(document.documentElement)
          .getPropertyValue("--top-menu-bar-height")
          .trim();

        if (height && height !== "") {
          const heightValue = parseFloat(height);
          if (!isNaN(heightValue) && heightValue > 0) {
            setHeaderHeight(heightValue);
          }
        }
      };

      // 초기 높이 설정
      updateHeightFromCSS();

      // CSS 변수 변경 감지를 위한 MutationObserver (최신 JS 기술)
      const observer = new MutationObserver(updateHeightFromCSS);
      observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["style"],
      });

      // 리사이즈 시 재계산
      window.addEventListener("resize", updateHeightFromCSS);

      return () => {
        observer.disconnect();
        window.removeEventListener("resize", updateHeightFromCSS);
      };
    }
  }, [isOpen]);

  useEffect(() => {
    if (isOpen) {
      // Initial fetch when drawer opens
      fetchWatchlist(true);
      loadGroups();

      // Set up real-time updates every 3 seconds
      const interval = setInterval(() => {
        fetchWatchlist(false);
      }, 3000);

      // Cleanup interval on unmount
      return () => {
        clearInterval(interval);
      };
    }
  }, [isOpen]);

  // Set first group as default when groups are loaded
  useEffect(() => {
    if (groups.length > 0 && selectedGroupId === null) {
      setSelectedGroupId(groups[0].id);
    }
  }, [groups, selectedGroupId]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (isGroupDropdownOpen && !target.closest(".group-dropdown-container")) {
        setIsGroupDropdownOpen(false);
      }
    };

    if (isGroupDropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => {
        document.removeEventListener("mousedown", handleClickOutside);
      };
    }
  }, [isGroupDropdownOpen]);

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ko-KR").format(price);
  };

  return (
    <>
      {/* Drawer */}
      <div
        className={`fixed left-0 top-0 h-full w-[20vw] min-w-[300px] max-w-[400px] bg-[#1a1a1a] border-r border-gray-800 z-50 transform transition-transform duration-300 ease-out ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{
          willChange: "transform",
          transitionTimingFunction: "cubic-bezier(0.4, 0, 0.2, 1)",
        }}
      >
        <div className="h-full flex flex-col">
          {/* Header - Sidebar + DashboardHeader 높이와 맞춤 (CSS Custom Property 사용) */}
          <div
            className="flex flex-col px-4 py-3 flex-shrink-0"
            style={{
              height: "var(--top-menu-bar-height, 76px)",
              minHeight: "var(--top-menu-bar-height, 76px)",
              maxHeight: "var(--top-menu-bar-height, 76px)",
            }}
          >
            <div className="flex flex-col">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                  관심 종목
                </h2>
                <button
                  onClick={onClose}
                  className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
                  title="닫기"
                >
                  <ChevronLeftIcon className="w-5 h-5 text-gray-600 dark:text-gray-400" />
                </button>
              </div>
              <div className="flex items-center justify-between">
                <button
                  onClick={() => setIsGroupDropdownOpen(!isGroupDropdownOpen)}
                  className="flex items-center gap-1 text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors"
                >
                  {groups.find((g) => g.id === selectedGroupId)?.name || ""}
                  <ChevronDownIcon className="w-3 h-3" />
                </button>
                <button
                  onClick={handleOpenEditModal}
                  className="flex items-center gap-1 px-3 py-1.5 bg-gray-700 dark:bg-gray-600 text-white rounded-full text-xs font-medium hover:bg-gray-600 dark:hover:bg-gray-500 transition-colors"
                  title="관심 종목 편집"
                >
                  <PencilSquareIcon className="w-3 h-3" />
                  편집
                </button>
              </div>
            </div>
          </div>

          {/* Groups Filter Dropdown - Hidden, shown in header */}
          {isGroupDropdownOpen && (
            <div className="group-dropdown-container absolute top-[var(--top-menu-bar-height,76px)] left-4 mt-1 w-48 bg-[#1a1a1a] border border-gray-800 rounded-lg shadow-lg z-50 max-h-60 overflow-y-auto">
              {groups.map((group) => (
                <div
                  key={group.id}
                  className="border-t border-gray-800 first:border-t-0"
                >
                  <button
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setSelectedGroupId(group.id);
                      setIsGroupDropdownOpen(false);
                    }}
                    className={`w-full px-3 py-2 text-xs font-medium text-left hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex items-center gap-2 ${
                      selectedGroupId === group.id
                        ? "bg-blue-50 dark:bg-blue-800/20 text-blue-500 dark:text-blue-400"
                        : "text-gray-700 dark:text-gray-300"
                    }`}
                  >
                    <div
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: group.color }}
                    ></div>
                    {group.name}
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Content */}
          <div className="flex-1 overflow-y-auto flex flex-col">
            {/* Add Stock Button at Top */}
            <div className="px-4 pt-6 pb-3 border-b border-gray-200 dark:border-gray-800 flex-shrink-0">
              <button
                onClick={() => setIsSearchOpen(true)}
                className="w-full flex items-center gap-3 text-left"
              >
                <div className="w-10 h-10 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center flex-shrink-0">
                  <PlusIcon className="w-5 h-5 text-blue-500 dark:text-blue-400" />
                </div>
                <span className="text-sm font-medium text-gray-900 dark:text-white">
                  종목추가
                </span>
              </button>
            </div>

            {/* Stock List */}
            <div className="flex-1 overflow-y-auto">
              {loading ? (
                <div className="p-4">
                  <div className="animate-pulse space-y-2">
                    {[...Array(5)].map((_, i) => (
                      <div
                        key={i}
                        className="h-12 bg-gray-200 dark:bg-gray-700 rounded"
                      ></div>
                    ))}
                  </div>
                </div>
              ) : filteredItems.length === 0 ? (
                <div className="p-4 text-center text-sm text-gray-500 dark:text-gray-400">
                  {selectedGroupId
                    ? "이 그룹에 속한 종목이 없습니다."
                    : "관심종목이 없습니다."}
                </div>
              ) : (
                <div>
                  {filteredItems.map((item) => {
                    const isPositive = item.changePercent >= 0;
                    const changeColorClass = isPositive
                      ? "text-red-600 dark:text-red-400"
                      : "text-blue-500 dark:text-blue-400";

                    return (
                      <div
                        key={item.symbol}
                        onClick={() => {
                          if (onStockSelect) {
                            onStockSelect(item.symbol, item.name);
                            // 드로어는 닫지 않고 유지
                          } else {
                            router.push(`/stock/${item.symbol}`);
                            onClose();
                          }
                        }}
                        className="px-4 py-3 hover:bg-[#252525] transition-colors cursor-pointer"
                      >
                        <div className="flex items-center gap-3 justify-between">
                          <div className="flex items-center gap-3 flex-1 min-w-0">
                            {/* Company Logo Placeholder */}
                            <div className="w-10 h-10 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center flex-shrink-0">
                              {item.logo ? (
                                <img
                                  src={item.logo}
                                  alt={item.name}
                                  className="w-10 h-10 rounded-full object-cover"
                                  loading="lazy"
                                />
                              ) : (
                                <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
                                  {item.name.charAt(0)}
                                </span>
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-medium text-gray-900 dark:text-white truncate">
                                {item.name}
                              </div>
                            </div>
                          </div>
                          <div className="flex flex-col items-end flex-shrink-0">
                            <span className="text-sm font-medium text-gray-900 dark:text-white">
                              {formatPrice(item.currentPrice)}원
                            </span>
                            <span
                              className={`text-xs ${changeColorClass} mt-0.5`}
                            >
                              {isPositive ? "+" : ""}
                              {formatPrice(Math.abs(item.change))}원 (
                              {isPositive ? "+" : ""}
                              {item.changePercent.toFixed(2)}%)
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Stock Search Modal */}
      <StockSearchModal
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        onSelect={handleAddToWatchlist}
      />

      {/* Edit Watchlist Modal */}
      {isEditModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-[60] flex items-center justify-center p-4">
          <div className="bg-[#1a1a1a] rounded-lg w-full max-w-5xl h-[80vh] flex flex-col">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-5">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                관심 종목 편집
              </h3>
              <button
                onClick={handleCloseEditModal}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                <XMarkIcon className="w-5 h-5 text-gray-500 dark:text-gray-400" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="flex-1 flex overflow-hidden border-t border-gray-800">
              {/* Left Side - Groups */}
              <div className="w-1/3 border-r border-gray-800 flex flex-col bg-[#0f0f0f]">
                <div className="p-4">
                  <button
                    onClick={openCreateGroupModal}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-600 transition-colors shadow-sm"
                  >
                    <PlusIcon className="w-4 h-4" />
                    그룹 추가
                  </button>
                </div>
                <div className="flex-1 overflow-y-auto px-2 pb-2">
                  <div className="space-y-1">
                    {groups.map((group) => (
                      <button
                        key={group.id}
                        onClick={() => setSelectedGroupForEdit(group.id)}
                        className={`w-full px-3 py-2.5 text-left rounded-lg transition-all ${
                          selectedGroupForEdit === group.id
                            ? "bg-blue-50 dark:bg-blue-800/20 text-blue-500 dark:text-blue-400 shadow-sm"
                            : "hover:bg-[#252525] text-gray-300"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium">
                            {group.name}
                          </span>
                          <span className="text-xs text-gray-400 bg-[#252525] px-2 py-0.5 rounded-full">
                            {getGroupItemCount(group.id)}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Right Side - Items */}
              <div className="flex-1 flex flex-col">
                {/* Action Bar */}
                <div className="p-4 bg-[#1a1a1a] flex items-center gap-3">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={
                        selectedGroupForEdit !== null &&
                        getItemsInGroup(selectedGroupForEdit).length > 0 &&
                        getItemsInGroup(selectedGroupForEdit).every((item) =>
                          selectedItemsForEdit.has(item.symbol)
                        )
                      }
                      onChange={(e) => {
                        const groupItems =
                          getItemsInGroup(selectedGroupForEdit);
                        if (e.target.checked) {
                          setSelectedItemsForEdit(
                            new Set(groupItems.map((item) => item.symbol))
                          );
                        } else {
                          setSelectedItemsForEdit(new Set());
                        }
                      }}
                      className="w-4 h-4 text-blue-500 border-gray-300 rounded focus:ring-blue-500"
                    />
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      이동
                    </span>
                  </label>
                  <button
                    onClick={handleDeleteSelectedItems}
                    disabled={selectedItemsForEdit.size === 0}
                    className="flex items-center gap-2 px-3 py-1.5 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <TrashIcon className="w-4 h-4" />
                    삭제
                  </button>
                  <button
                    onClick={() => setIsSearchOpen(true)}
                    className="flex items-center gap-2 px-3 py-1.5 text-sm text-blue-500 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-800/20 rounded transition-colors"
                  >
                    <PlusIcon className="w-4 h-4" />
                    종목 추가
                  </button>
                  <div className="ml-auto flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                    <ArrowsUpDownIcon className="w-4 h-4" />
                    직접 설정한 순
                  </div>
                </div>

                {/* Items List */}
                <div className="flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-900/30">
                  {selectedGroupForEdit === null ? (
                    <div className="p-8 text-center text-sm text-gray-500 dark:text-gray-400">
                      그룹을 선택해주세요.
                    </div>
                  ) : getItemsInGroup(selectedGroupForEdit).length === 0 ? (
                    <div className="p-8 text-center text-sm text-gray-500 dark:text-gray-400">
                      이 그룹에 종목이 없습니다.
                    </div>
                  ) : (
                    <div className="p-2 space-y-1">
                      {getItemsInGroup(selectedGroupForEdit).map(
                        (item, index) => {
                          const isSelected = selectedItemsForEdit.has(
                            item.symbol
                          );

                          return (
                            <div
                              key={item.symbol}
                              className={`px-4 py-3 rounded-lg flex items-center gap-3 transition-all ${
                                isSelected
                                  ? "bg-blue-50 dark:bg-blue-800/20 border border-blue-200 dark:border-blue-800"
                                  : "bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/50"
                              }`}
                            >
                              <Bars3Icon className="w-5 h-5 text-gray-400 dark:text-gray-500 cursor-move" />
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() =>
                                  handleToggleItemSelection(item.symbol)
                                }
                                onClick={(e) => e.stopPropagation()}
                                className="w-4 h-4 text-blue-500 border-gray-300 rounded focus:ring-blue-500"
                              />
                              <div className="w-10 h-10 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center flex-shrink-0">
                                {item.logo ? (
                                  <img
                                    src={item.logo}
                                    alt={item.name}
                                    className="w-10 h-10 rounded-full object-cover"
                                  />
                                ) : (
                                  <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
                                    {item.name.charAt(0)}
                                  </span>
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium text-gray-900 dark:text-white truncate">
                                  {item.name}
                                </div>
                              </div>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (
                                    confirm(
                                      `${item.name}을(를) 삭제하시겠습니까?`
                                    )
                                  ) {
                                    removeFromWatchlist(item.symbol);
                                    fetchWatchlist(false);
                                  }
                                }}
                                className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors"
                              >
                                <XMarkIcon className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                              </button>
                            </div>
                          );
                        }
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Group Modal */}
      {isGroupModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md mx-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              {editingGroup ? "그룹 수정" : "그룹 생성"}
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  그룹 이름
                </label>
                <input
                  type="text"
                  value={groupName}
                  onChange={(e) => setGroupName(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="그룹 이름을 입력하세요"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  색상
                </label>
                <input
                  type="color"
                  value={groupColor}
                  onChange={(e) => setGroupColor(e.target.value)}
                  className="w-full h-10 border border-gray-300 dark:border-gray-600 rounded-lg cursor-pointer"
                />
              </div>
              <div className="flex items-center gap-2 justify-end">
                <button
                  onClick={closeGroupModal}
                  className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-200 dark:bg-gray-700 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                >
                  취소
                </button>
                <button
                  onClick={editingGroup ? handleUpdateGroup : handleCreateGroup}
                  className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-600 transition-colors"
                >
                  {editingGroup ? "수정" : "생성"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// React.memo로 감싸서 리렌더링 방지 - props가 변경되지 않으면 리렌더링하지 않음
// 커스텀 비교 함수로 불필요한 리렌더링 방지
export default memo(WatchlistDrawer, (prevProps, nextProps) => {
  // isOpen이 변경되지 않았고, 함수 참조가 동일하면 리렌더링하지 않음
  return (
    prevProps.isOpen === nextProps.isOpen &&
    prevProps.onClose === nextProps.onClose &&
    prevProps.onStockSelect === nextProps.onStockSelect
  );
});
