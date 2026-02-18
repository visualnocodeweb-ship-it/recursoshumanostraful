import React from 'react';
import './MainMenu.css';

function MainMenu({ onSelectModule }) {
  const modules = [
    'Certificado Medico',
    'Licencia',
    'Formulario 81_inciso_D',
    'Formulario 81_inciso_F',
    'Control de Envíos'
  ];

  return (
    <div className="main-menu-container">
      {modules.map(moduleName => (
        <button
          key={moduleName}
          className="module-button"
          onClick={() => onSelectModule(moduleName)}
        >
          {moduleName}
        </button>
      ))}
    </div>
  );
}

export default MainMenu;
