          {currentStep === 2 && (
            <div className="flex flex-col min-h-full">
              <div 
                ref={canvasRef}
                className="flex-1 relative"
                style={{ minHeight: canvasMinHeight }}
              onDragOver={(e) => {
                e.preventDefault();
                setDraggedOver(true);
              }}
              onDragLeave={() => setDraggedOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDraggedOver(false);
                const blockId = e.dataTransfer.getData("blockId");
                const blockType = e.dataTransfer.getData("blockType");
                const moveBlockId = e.dataTransfer.getData("moveBlockId"); // Check if moving existing block

                if (blockId) {
                  // Adding new block - coordinates no longer matter as they will be auto-aligned
                  if (canvasBlocks.some(b => b.blockId === blockId)) {
                    alert("이미 추가된 블록입니다");
                    return;
                  }

                  const newBlock: CanvasBlock = {
                    id: Math.random().toString(36).substr(2, 9),
                    type: blockType?.includes("risk") ? "exit" : blockType?.includes("filter") ? "filter" : "entry",
                    blockId: blockId,
                    position: { x: 0, y: 0 }, // Position will be calculated during render
                    params: {},
                  };

                  // Smart Insertion Logic: Group same-type blocks together to maintain connections
                  const isEntryOrFilter = (t: string) => t === "entry" || t === "filter";
                  const isExit = (t: string) => t === "exit";
                  
                  const newType = newBlock.type;
                  let insertIndex = canvasBlocks.length;

                  // Find the last index of a block from the same logical group
                  for (let i = canvasBlocks.length - 1; i >= 0; i--) {
                    const currentType = canvasBlocks[i].type;
                    if (
                      (isEntryOrFilter(newType) && isEntryOrFilter(currentType)) ||
                      (isExit(newType) && isExit(currentType))
                    ) {
                      insertIndex = i + 1;
                      break;
                    }
                  }

                  // If no similar blocks found, and it's an Entry/Filter, maybe put it at the start or before Exits
                  if (insertIndex === canvasBlocks.length && isEntryOrFilter(newType)) {
                    const firstExitIndex = canvasBlocks.findIndex(b => isExit(b.type));
                    if (firstExitIndex !== -1) {
                      insertIndex = firstExitIndex;
                    }
                  }

                  const updatedBlocks = [...canvasBlocks];
                  updatedBlocks.splice(insertIndex, 0, newBlock);
                  
                  setCanvasBlocks(updatedBlocks);
                  setSelectedBlock(newBlock);
                }
              }}
            >
              {/* Grid Background */}
              <div className="absolute inset-0 pointer-events-none opacity-20"
                style={{
                  backgroundImage: "radial-gradient(#4b5563 1px, transparent 1px)",
                  backgroundSize: "20px 20px"
                }}
              />

              {/* Watermark/Instruction */}
              {canvasBlocks.length === 0 && (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-600 pointer-events-none">
                  <CubeIcon className="w-16 h-16 mb-4 opacity-20" />
                  <p className="text-lg">왼쪽 라이브러리에서 블록을 드래그하세요</p>
                </div>
              )}

              {/* Canvas Content */}
              <div className="absolute inset-0">
                {/* SVG Connections Layer */}
                <svg className="absolute inset-0 w-full h-full pointer-events-none z-0">
                  <defs>
                    <marker
                      id="arrowhead"
                      markerWidth="10"
                      markerHeight="7"
                      refX="9"
                      refY="3.5"
                      orient="auto"
                    >
                      <polygon points="0 0, 10 3.5, 0 7" fill="#4B5563" />
                    </marker>
                  </defs>
                  {/* Sequential Flow Connections */}
                  {canvasBlocks.map((block, index) => {
                    if (index === canvasBlocks.length - 1) return null;
                    const nextBlock = canvasBlocks[index + 1];

                    // Determine if we should draw a connection between these two blocks
                    // Connections are only drawn if both blocks are in the same logic group AND that group's logic is 'AND'
                    const isEntryOrFilter = (b: CanvasBlock) => b.type === "entry" || b.type === "filter";
                    const isExit = (b: CanvasBlock) => b.type === "exit";

                    let shouldConnect = false;
                    if (isEntryOrFilter(block) && isEntryOrFilter(nextBlock)) {
                      shouldConnect = entryLogic === "AND";
                    } else if (isExit(block) && isExit(nextBlock)) {
                      shouldConnect = exitLogic === "AND";
                    }
                    
                    if (!shouldConnect) return null;
                    
                    const col = index % blocksPerRow;
                    const row = Math.floor(index / blocksPerRow);
                    const nextCol = (index + 1) % blocksPerRow;
                    const nextRow = Math.floor((index + 1) / blocksPerRow);
                    
                    const startX = sidePadding + col * 155 + 130; // Right side of 130px width block
                    const startY = 60 + row * 110 + 40;  
                    const endX = sidePadding + nextCol * 155;     // Left side of next block
                    const endY = 60 + nextRow * 110 + 40; 

                    // Adjust control points for wrapping rows
                    const isWrap = nextRow > row;
                    const cp1x = isWrap ? startX + 40 : startX + 20;
                    const cp1y = isWrap ? startY + 40 : startY;
                    const cp2x = isWrap ? endX - 40 : endX - 20;
                    const cp2y = isWrap ? endY - 40 : endY;

                    return (
                      <path
                        key={`flow-${block.id}-${nextBlock.id}`}
                        d={`M ${startX} ${startY} C ${cp1x} ${cp1y} ${cp2x} ${cp2y} ${endX} ${endY}`}
                        stroke="#4B5563"
                        strokeWidth="2"
                        fill="none"
                        markerEnd="url(#arrowhead)"
                        className="opacity-30"
                      />
                    );
                  })}
                </svg>
                
                {/* Render canvas blocks in a sequential grid layout */}
                {canvasBlocks.map((block, index) => {
                  const colIdx = index % blocksPerRow;
                  const rowIdx = Math.floor(index / blocksPerRow);
                  const xOffset = sidePadding + colIdx * 155; // centered start + col * spacing
                  const yOffset = 60 + rowIdx * 110; // 80 height + 30 gap
                  
                  // Determine styles based on block type
                  let typeStyles = "border-gray-700 bg-[#1a1a1a]/80";
                  if (block.type === "entry") {
                    typeStyles = "border-red-500/30 bg-red-500/10 hover:bg-red-500/20 shadow-[0_4px_12px_rgba(239,68,68,0.1)]";
                  } else if (block.type === "exit") {
                    typeStyles = "border-blue-500/30 bg-blue-500/10 hover:bg-blue-500/20 shadow-[0_4px_12px_rgba(59,130,246,0.1)]";
                  } else if (block.type === "filter") {
                    typeStyles = "border-purple-500/30 bg-purple-500/10 hover:bg-purple-500/20 shadow-[0_4px_12px_rgba(168,85,247,0.1)]";
                  }

                  const isSelected = selectedBlock?.id === block.id;
                    
                    return (
                      <div
                        key={block.id}
                        onClick={() => setSelectedBlock(block)}
                        className={`absolute p-3 rounded-lg transition-all duration-300 backdrop-blur-md border group ${typeStyles} ${
                          isSelected
                            ? "ring-2 ring-offset-2 ring-offset-[#0f0f0f] ring-blue-500 shadow-[0_0_20px_rgba(59,130,246,0.3)] z-10 scale-105"
                            : "hover:scale-105 hover:border-opacity-50 hover:shadow-xl z-1"
                        }`}
                        style={{
                          left: `${xOffset}px`,
                          top: `${yOffset}px`,
                          width: "130px",
                        }}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              block.type === "entry"
                                ? "bg-green-400 shadow-[0_0_5px_rgba(74,222,128,0.5)]"
                                : block.type === "exit"
                                ? "bg-red-400 shadow-[0_0_5px_rgba(248,113,113,0.5)]"
                                : "bg-purple-400 shadow-[0_0_5px_rgba(192,132,252,0.5)]"
                            }`}
                          />
                          <span className="text-[8px] text-gray-500 font-bold uppercase tracking-tighter opacity-0 group-hover:opacity-100">
                            {block.type}
                          </span>
                        </div>
                        <div className="text-[11px] font-bold text-white/90 whitespace-normal break-words leading-tight">
                          {signalBlocks[block.blockId]?.name || block.blockId}
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setCanvasBlocks(canvasBlocks.filter(b => b.id !== block.id));
                            if (selectedBlock?.id === block.id) {
                              setSelectedBlock(null);
                            }
                          }}
                          className="absolute -top-1.5 -right-1.5 w-5 h-5 flex items-center justify-center bg-[#1a1a1a] border border-gray-800 text-gray-500 hover:text-white rounded-full transition-all shadow-lg opacity-0 group-hover:opacity-100"
                        >
                          <XMarkIcon className="w-2.5 h-2.5" />
                        </button>
                      </div>
                    );
                  })}
                </div>

                {/* Sticky Navigation Footer */}
                <div className="sticky bottom-0 bg-[#0a0a0a]/90 backdrop-blur-xl border-t border-gray-800/50 p-6 flex justify-end gap-3 z-50 mt-auto">
                  <button
                    onClick={() => setCurrentStep(1)}
                    className="px-6 py-3 bg-[#1a1a1a] border border-gray-800 text-gray-300 rounded-xl text-md font-black hover:bg-gray-800 hover:text-white transition-all flex items-center gap-2 shadow-xl"
                  >
                    <ArrowLeftIcon className="w-5 h-5" />
                    이전 단계
                  </button>
                  <button
                    onClick={() => setCurrentStep(3)}
                    className="px-8 py-3 bg-blue-600 text-white rounded-xl text-md font-black hover:bg-blue-500 transition-all flex items-center gap-3 shadow-xl shadow-blue-900/40 hover:scale-[1.02]"
                  >
                    다음: 포지션/비중
                    <ArrowRightIcon className="w-5 h-5" />
                  </button>
                </div>
              </div>
            )}

