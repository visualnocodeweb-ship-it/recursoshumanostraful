import React, { useState } from 'react';
import './App.css';
import SheetData from './SheetData'; // The component for "Certificado Medico"
import LicenciaData from './LicenciaData'; // New component for "Licencia"
import Formulario81DData from './Formulario81DData'; // New component for "Formulario 81_inciso_D"
import Formulario81FData from './Formulario81FData'; // New component for "Formulario 81_inciso_F"
import MainMenu from './MainMenu';   // The new menu component

function App() {
  const [selectedModule, setSelectedModule] = useState(null);

  const handleSelectModule = (moduleName) => {
    setSelectedModule(moduleName);
  };

  const handleBackToMenu = () => {
    setSelectedModule(null);
  };

  const renderModule = () => {
    switch (selectedModule) {
      case 'Certificado Medico':
        return <SheetData onBackToMenu={handleBackToMenu} />;
      case 'Licencia':
        return <LicenciaData onBackToMenu={handleBackToMenu} />;
      case 'Formulario 81_inciso_D':
        return <Formulario81DData onBackToMenu={handleBackToMenu} />; // Render Formulario81DData
      case 'Formulario 81_inciso_F':
        return <Formulario81FData onBackToMenu={handleBackToMenu} />; // Render Formulario81FData
      default:
        return <MainMenu onSelectModule={handleSelectModule} />;
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Tablero de Recursos Humanos</h1>
        <div className="profile-icon">
          <span>TF</span> {/* Changed to TF for Traful */}
        </div>
      </header>

      <main>
        {renderModule()}
      </main>
    </div>
  );
}

export default App;