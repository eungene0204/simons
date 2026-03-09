import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import Step2Conditions from '../Step2Conditions';
import { CanvasBlock } from '@/types/strategy';

// Mock framer-motion to avoid animation issues in tests
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    h2: ({ children, ...props }: any) => <h2 {...props}>{children}</h2>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

// Mock phosphor-react icons
vi.mock('phosphor-react', () => ({
  X: () => <svg data-testid="icon-x" />,
  Sliders: () => <svg data-testid="icon-sliders" />,
  Question: () => <svg data-testid="icon-question" />,
  CaretDown: () => <svg data-testid="icon-caret-down" />,
  CaretUp: () => <svg data-testid="icon-caret-up" />,
  Info: () => <svg data-testid="icon-info" />,
  Plus: () => <svg data-testid="icon-plus" />,
  MagnifyingGlass: () => <svg data-testid="icon-magnifying-glass" />,
  ArrowRight: () => <svg data-testid="icon-arrow-right" />,
  ArrowLeft: () => <svg data-testid="icon-arrow-left" />,
  Cube: () => <svg data-testid="icon-cube" />,
  Sparkle: () => <svg data-testid="icon-sparkle" />,
  ShieldWarning: () => <svg data-testid="icon-shield-warning" />,
  Cpu: () => <svg data-testid="icon-cpu" />,
  ChartBar: () => <svg data-testid="icon-chart-bar" />,
  ArrowsClockwise: () => <svg data-testid="icon-arrows-clockwise" />,
  Bank: () => <svg data-testid="icon-bank" />,
  ChartPie: () => <svg data-testid="icon-chart-pie" />,
  DotsThreeOutline: () => <svg data-testid="icon-dots-three-outline" />,
  HandPointing: () => <svg data-testid="icon-hand-pointing" />,
  SquaresFour: () => <svg data-testid="icon-squares-four" />,
  List: () => <svg data-testid="icon-list" />,
  Globe: () => <svg data-testid="icon-globe" />,
  Database: () => <svg data-testid="icon-database" />,
  FramerLogo: () => <svg data-testid="icon-framer-logo" />,
}));

const mockProps: any = {
  canvasBlocks: [
    { id: '1', type: 'entry', blockId: 'ma_crossover', position: { x: 0, y: 0 }, params: {}, logic: 'AND' },
    { id: '2', type: 'entry', blockId: 'rsi', position: { x: 0, y: 0 }, params: {}, logic: 'AND' },
  ],
  setCanvasBlocks: vi.fn(),
  selectedBlock: { id: '1', type: 'entry', blockId: 'ma_crossover', position: { x: 0, y: 0 }, params: {}, logic: 'AND' },
  setSelectedBlock: vi.fn(),
  activeParamTab: 'block',
  setActiveParamTab: vi.fn(),
  entryLogic: 'AND',
  setEntryLogic: vi.fn(),
  exitLogic: 'OR',
  setExitLogic: vi.fn(),
  unlockedBlockIds: [],
  setUnlockedBlockIds: vi.fn(),
  manuallyHiddenBlockIds: [],
  setManuallyHiddenBlockIds: vi.fn(),
  customBlockOrder: {},
  setCustomBlockOrder: vi.fn(),
  customCategoryOrder: [],
  setCustomCategoryOrder: vi.fn(),
  hoveredInfo: null,
  setHoveredInfo: vi.fn(),
  hoveredParam: null,
  setHoveredParam: vi.fn(),
  hoveredEditIcon: null,
  setHoveredEditIcon: vi.fn(),
  isSearchMenuOpen: false,
  setIsSearchMenuOpen: vi.fn(),
  isLibraryManagementOpen: false,
  setIsLibraryManagementOpen: vi.fn(),
  activeMgmtCategory: 'indicator',
  setActiveMgmtCategory: vi.fn(),
  draggedModalItemIndex: null,
  setDraggedModalItemIndex: vi.fn(),
  draggedCategoryIndex: null,
  setDraggedCategoryIndex: vi.fn(),
  openSignalGroups: [],
  setOpenSignalGroups: vi.fn(),
  savedFeedback: null,
  setSavedFeedback: vi.fn(),
  reorderDragItem: null,
  setReorderDragItem: vi.fn(),
  canvasRef: { current: null },
  canvasWidth: 1000,
  onNext: vi.fn(),
  onPrev: vi.fn(),
  handleAddBlock: vi.fn(),
  handleRemoveBlockFromBin: vi.fn(),
};

describe('Step2Conditions Logic Buttons', () => {
  it('should update only the selected block logic when a logic button is clicked', () => {
    render(<Step2Conditions {...mockProps} />);

    // Find the OR button in the property editor
    // Note: The logic buttons are rendered when selectedBlock is truthy
    const orButton = screen.getByRole('button', { name: /OR/i });
    expect(orButton).toBeInTheDocument();

    // Click OR button
    fireEvent.click(orButton);

    // Verify setCanvasBlocks was called with updated logic for block '1'
    expect(mockProps.setCanvasBlocks).toHaveBeenCalled();
    const updatedBlocks = mockProps.setCanvasBlocks.mock.calls[0][0];
    
    // Check that block '1' is now OR
    const block1 = updatedBlocks.find((b: any) => b.id === '1');
    expect(block1.logic).toBe('OR');

    // Check that block '2' remains AND (decoupled behavior)
    const block2 = updatedBlocks.find((b: any) => b.id === '2');
    expect(block2.logic).toBe('AND');
    
    // Check that setSelectedBlock was also called to update the editor state
    expect(mockProps.setSelectedBlock).toHaveBeenCalledWith(expect.objectContaining({
      id: '1',
      logic: 'OR'
    }));
  });

  it('should not call setEntryLogic or setExitLogic (global logic) when a individual block logic is clicked', () => {
    mockProps.setCanvasBlocks.mockClear();
    mockProps.setEntryLogic.mockClear();
    mockProps.setExitLogic.mockClear();

    render(<Step2Conditions {...mockProps} />);

    const orButton = screen.getByRole('button', { name: /OR/i });
    fireEvent.click(orButton);

    // Should NOT update global logic (this verifies the removal of global sync)
    expect(mockProps.setEntryLogic).not.toHaveBeenCalled();
    expect(mockProps.setExitLogic).not.toHaveBeenCalled();
  });
});
