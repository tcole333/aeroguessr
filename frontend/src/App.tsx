import React from "react";

function App() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4">
      <div className="card p-6 max-w-md w-full">
        <h1 className="text-center mb-6">Plane Guessing Game</h1>
        <p className="text-secondary-600 dark:text-secondary-400 mb-4 text-center">
          Welcome to the real-time flight tracking game.
        </p>
        <div className="flex justify-center">
          <button className="btn-primary">Start Game</button>
        </div>
      </div>
    </div>
  );
}

export default App;
