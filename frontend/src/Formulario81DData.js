import React, { useEffect, useState, useMemo } from 'react';
import './Formulario81DData.css'; // Will create this file for card-specific styles
import API_URL from './apiConfig'; // Import the API URL

// Nuevo componente Card para manejar la lógica de colapsado
function Formulario81DDataCard({ row, headers }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isSendingEmail, setIsSendingEmail] = useState(false); // Nuevo estado para el envío de email
  const [emailSendStatus, setEmailSendStatus] = useState(null); // 'success', 'error'
  const [emailSendError, setEmailSendError] = useState(null); // Mensaje de error

  const toggleExpand = () => {
    setIsExpanded(!isExpanded);
  };

  const nameHeader = headers.find(h => ['name'].includes(h.toLowerCase()));
  const surnameHeader = headers.find(h => ['apellido', 'legajo'].includes(h.toLowerCase())); // 'legajo' can also act as surname
  const emailHeader = headers.find(h => ['email'].includes(h.toLowerCase())); // Encontrar el encabezado del email

  const hiddenItems = headers.filter(header =>
    header !== nameHeader && header !== surnameHeader && header !== 'pdf_drive_id' && header !== emailHeader
  );

  const pdfDriveId = row['pdf_drive_id'];
  const hasPdfLink = !!pdfDriveId;
  const recipientEmail = emailHeader ? row[emailHeader] : null;
  const canSendEmail = hasPdfLink && recipientEmail; // Solo enviar si hay PDF y email

  const handleSendPdfEmail = async () => {
    if (!canSendEmail) return;

    setIsSendingEmail(true);
    setEmailSendStatus(null);
    setEmailSendError(null);

    try {
      const response = await fetch(`${API_URL}/send_pdf_email`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          pdf_drive_id: pdfDriveId,
          recipient_email: recipientEmail,
          subject: `Autorización de Formulario 81 Inciso D para ${row[nameHeader] || ''} ${row[surnameHeader] || ''}`, // Asunto dinámico
          body_text: `Estimado/a,

Adjuntamos la autorización de Formulario 81 Inciso D para ${row[nameHeader] || ''} ${row[surnameHeader] || ''}.

Saludos,
Recursos Humanos Traful`, // Cuerpo dinámico
          filename: `Formulario_81D_${row[nameHeader] || ''}_${row[surnameHeader] || ''}.pdf`, // Nombre de archivo sugerido
          sheet_row_number: row['sheet_row_number'], // Añadido para actualizar la hoja de cálculo
          sheet_name: "81_inciso_D", // Especificar la hoja '81_inciso_D'
          update_column_letter: "J" // Especificar la columna 'J' para 'Envio' en la hoja '81_inciso_D'
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Error al enviar el email.');
      }

      setEmailSendStatus('success');
    } catch (error) {
      console.error('Error sending email:', error);
      setEmailSendStatus('error');
      setEmailSendError(error.message);
    } finally {
      setIsSendingEmail(false);
    }
  };

  return (
    <div className="data-card">
      <div className="card-header-row">
        <div className="name-surname-container">
          {nameHeader || surnameHeader ? (
            <span className="card-main-info combined-name">
              {`${row[surnameHeader] || '-'}, ${row[nameHeader] || '-'}`}
            </span>
          ) : (
            <span className="card-main-info combined-name">
              {(headers.length > 0 ? (row[headers[0]] || '-') : '') +
               (headers.length > 1 ? (', ' + (row[headers[1]] || '-')) : '')}
            </span>
          )}
        </div>
        {(hiddenItems.length > 0 || hasPdfLink || canSendEmail) && (
          <button onClick={toggleExpand} className="toggle-button">
            {isExpanded ? '-' : '+'}
          </button>
        )}
      </div>

      {isExpanded && (
        <>
          {hasPdfLink && (
            <div className="card-item hidden-item pdf-link-item">
              <span className="card-label">PDF:</span>
              <span className="card-value">
                <a href={`https://drive.google.com/uc?export=download&id=${pdfDriveId}`} target="_blank" rel="noopener noreferrer">
                  Ver PDF
                </a>
              </span>
            </div>
          )}

          {/* Botón "Enviar autorización" */}
          <div className="card-item hidden-item">
            <button
              onClick={handleSendPdfEmail}
              disabled={!canSendEmail || isSendingEmail}
              className={`send-email-button ${isSendingEmail ? 'sending' : ''} ${emailSendStatus || ''}`}
            >
              {isSendingEmail ? 'Enviando...' : 'Enviar autorización'}
            </button>
            {emailSendStatus === 'success' && <span className="email-status success">✓ Enviado</span>}
            {emailSendStatus === 'error' && <span className="email-status error">✗ Error: {emailSendError}</span>}
          </div>

          {/* Render other hidden items */}
          {hiddenItems.map((header, index) => (
            <div key={index} className="card-item hidden-item">
              <span className="card-label">{header}:</span>
              {/* If original 'certificado_adjunto' was present and there's no pdfDriveId, show it as a fallback link */}
              {header.toLowerCase() === 'certificado_adjunto' && row[header] && !hasPdfLink ? (
                <span className="card-value">
                  <a href={row[header]} target="_blank" rel="noopener noreferrer">Ver Certificado (anterior)</a>
                </span>
              ) : (
                <span className="card-value">{row[header] || '-'}</span>
              )}
            </div>
          ))}
          
          {/* Message if no PDF link and no other hidden items to show */}
          {!hasPdfLink && hiddenItems.length === 0 && (
            <div className="card-item hidden-item">
              <span className="card-value no-pdf-message">No hay detalles adicionales.</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}


function Formulario81DData({ onBackToMenu }) { // Accept onBackToMenu prop
  const [data, setData] = useState({ headers: [], data: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const recordsPerPage = 10;

  useEffect(() => {
    const fetchFormulario81DData = async () => {
      try {
        const spreadsheetId = '1VohQVfx1rmnV8nkT3cxQdx996bj0BkeLovAmqYZXuMA'; // Tu ID de Google Sheet
        const rangeName = '81_inciso_D!A1:J'; // Nombre de hoja y rango para Formulario 81 Inciso D

        const requestUrl = `${API_URL}/sheets/formulario-81-d-data?spreadsheet_id=${spreadsheetId}&range_name=${rangeName}`;


        const response = await fetch(requestUrl);
        
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const result = await response.json();
        // Reverse the data array to show latest first
        setData({ headers: result.headers, data: result.data.slice().reverse() });
      } catch (e) {
        setError(e);
      } finally {
        setLoading(false);
      }
    };

    fetchFormulario81DData();
  }, []);

  const filteredData = useMemo(() => {
    if (!searchTerm) {
      return data.data;
    }
    return data.data.filter(row =>
      Object.values(row).some(value =>
        String(value).toLowerCase().includes(searchTerm.toLowerCase())
      )
    );
  }, [data.data, searchTerm]);

  // Pagination logic
  const indexOfLastRecord = currentPage * recordsPerPage;
  const indexOfFirstRecord = indexOfLastRecord - recordsPerPage;
  const currentRecords = filteredData.slice(indexOfFirstRecord, indexOfLastRecord);
  const nPages = Math.ceil(filteredData.length / recordsPerPage);

  const paginate = (pageNumber) => setCurrentPage(pageNumber);

  if (loading) return <div className="loading-message">Cargando datos de Formulario 81 Inciso D...</div>;
  if (error) return <div className="error-message">Error: {error.message}</div>;

  return (
    <div className="sheet-data-wrapper">
      <div className="controls-container">
        <button onClick={onBackToMenu} className="back-button">← Volver al Menú</button>
        <input
          type="text"
          placeholder="Buscar en los registros de Formulario 81 Inciso D..."
          className="search-bar"
          onChange={(e) => {
            setSearchTerm(e.target.value);
            setCurrentPage(1); // Reset to first page on new search
          }}
        />
      </div>

      <div className="sheet-data-container">
        {currentRecords.length > 0 ? (
          currentRecords.map((row, rowIndex) => (
            <Formulario81DDataCard key={rowIndex} row={row} headers={data.headers} />
          ))
        ) : (
          <p className="no-data-message">No se encontraron registros de Formulario 81 Inciso D.</p>
        )}
      </div>
      
      {nPages > 1 && (
        <div className="pagination">
          <button
            onClick={() => paginate(currentPage - 1)}
            disabled={currentPage === 1}
          >
            Anterior
          </button>
          <span>Página {currentPage} de {nPages}</span>
          <button
            onClick={() => paginate(currentPage + 1)}
            disabled={currentPage === nPages}
          >
            Siguiente
          </button>
        </div>
      )}
    </div>
  );
}

export default Formulario81DData;
