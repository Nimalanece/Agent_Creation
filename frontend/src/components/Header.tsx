import React from "react";

const Header: React.FC = () => {
  return (
    <header className="border-b border-slate-700/40 bg-slate-950/60 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-blue-500 to-violet-500 text-sm font-bold text-white shadow-lg shadow-blue-500/20">AQ</div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-white">AI QA Agent</h1>
          </div>
        </div>
        <div className="hidden items-center gap-3 text-xs text-slate-400 sm:flex">
          <span className="h-2 w-2 rounded-full bg-green-400 shadow-sm shadow-green-400/70" />
          Pipeline ready
        </div>
      </div>
    </header>
  );
};

export default Header;
