import React, { useState, useRef, useEffect } from 'react';
import { 
  UploadCloud, 
  FileImage, 
  Film, 
  CheckCircle2, 
  AlertTriangle, 
  ShieldCheck, 
  ShieldAlert, 
  HelpCircle, 
  Save, 
  RefreshCw, 
  Layers, 
  Play, 
  X
} from 'lucide-react';
import api, { AI_BASE_URL } from '../services/api';

export default function UploadDetectionPage() {
  const [file, setFile] = useState(null);
  const [filePreview, setFilePreview] = useState(null);
  const [fileType, setFileType] = useState(''); // 'image' | 'video'
  const [isProcessing, setIsProcessing] = useState(false);
  const [progressPercent, setProgressPercent] = useState(0);
  const [zones, setZones] = useState([]);
  const [selectedZoneId, setSelectedZoneId] = useState('');
  const [selectedZone, setSelectedZone] = useState(null);
  const [saveSuccess, setSaveSuccess] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // Results
  const [detectionResult, setDetectionResult] = useState(null);
  const [videoFramesResult, setVideoFramesResult] = useState(null);

  const fileInputRef = useRef(null);

  useEffect(() => {
    const fetchZones = async () => {
      try {
        const res = await api.get('/zones');
        const activeZones = res.data.filter((z) => z.active);
        setZones(activeZones);
        if (activeZones.length > 0) {
          setSelectedZoneId(activeZones[0]._id);
          setSelectedZone(activeZones[0]);
        }
      } catch (err) {
        console.error('Error fetching zones:', err);
      }
    };
    fetchZones();
  }, []);

  useEffect(() => {
    const found = zones.find((z) => z._id === selectedZoneId);
    if (found) setSelectedZone(found);
  }, [selectedZoneId, zones]);

  const handleFileChange = (e) => {
    setErrorMsg('');
    setDetectionResult(null);
    setVideoFramesResult(null);
    const selected = e.target.files[0];
    if (!selected) return;

    // Validate size (max 50MB)
    if (selected.size > 50 * 1024 * 1024) {
      setErrorMsg('File exceeds 50MB maximum allowable limit.');
      return;
    }

    if (selected.type.startsWith('image/')) {
      setFileType('image');
      setFile(selected);
      setFilePreview(URL.createObjectURL(selected));
    } else if (selected.type.startsWith('video/')) {
      setFileType('video');
      setFile(selected);
      setFilePreview(URL.createObjectURL(selected));
    } else {
      setErrorMsg('Unsupported file format. Please upload JPG, PNG, or MP4/WebM.');
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const dropped = e.dataTransfer.files[0];
      const fakeEvent = { target: { files: [dropped] } };
      handleFileChange(fakeEvent);
    }
  };

  const clearFile = () => {
    setFile(null);
    setFilePreview(null);
    setDetectionResult(null);
    setVideoFramesResult(null);
    setErrorMsg('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // Run AI Detection on Uploaded Media
  const runDetection = async () => {
    if (!file) return;
    setIsProcessing(true);
    setErrorMsg('');
    setProgressPercent(10);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('required_ppe', JSON.stringify(selectedZone?.requiredPPE || ['helmet', 'vest']));
    formData.append('zone_name', selectedZone?.name || 'Inspection Zone');

    try {
      if (fileType === 'image') {
        setProgressPercent(40);
        const res = await fetch(`${AI_BASE_URL}/detect`, {
          method: 'POST',
          body: formData,
        });

        if (!res.ok) {
          throw new Error('AI detection service returned an error');
        }

        setProgressPercent(85);
        const data = await res.json();
        setDetectionResult({
          complianceStatus: data.compliance_status || 'UNCERTAIN',
          missingPPE: data.missing_ppe || [],
          detectedClasses: data.detected_classes || [],
          persons: data.persons || [],
          annotatedImage: data.annotated_image ? `data:image/jpeg;base64,${data.annotated_image}` : filePreview,
          latencyMs: data.latency_ms || 120,
        });
      } else {
        // Video upload detection
        setProgressPercent(30);
        const res = await fetch(`${AI_BASE_URL}/detect-video`, {
          method: 'POST',
          body: formData,
        });

        if (!res.ok) {
          throw new Error('AI video detection service returned an error');
        }

        setProgressPercent(85);
        const data = await res.json();
        setVideoFramesResult(data);
        setDetectionResult({
          complianceStatus: data.overall_compliance_status || 'UNCERTAIN',
          missingPPE: data.overall_missing_ppe || [],
          detectedClasses: data.overall_detected_classes || [],
          persons: data.persons || [],
          totalFrames: data.total_frames_processed || 0,
          violationsCount: data.total_violations_found || 0,
        });
      }
      setProgressPercent(100);
    } catch (err) {
      console.error('Detection error:', err);
      setErrorMsg(`Detection failed: ${err.message}. Ensure AI Flask Service is running on port 5001.`);
    } finally {
      setIsProcessing(false);
    }
  };

  // Save Event to MongoDB
  const saveEventToDB = async () => {
    if (!detectionResult) return;
    try {
      await api.post('/detections', {
        zoneId: selectedZone?._id,
        zoneName: selectedZone?.name || 'Uploaded File',
        sourceType: fileType,
        detectedClasses: detectionResult.detectedClasses,
        missingPPE: detectionResult.missingPPE,
        complianceStatus: detectionResult.complianceStatus,
        personCount: detectionResult.persons?.length || 1,
        evidenceImageBase64: detectionResult.annotatedImage || null,
        processingMetadata: {
          fileType,
          fileName: file?.name,
          latencyMs: detectionResult.latencyMs,
        },
      });

      setSaveSuccess('Detection record successfully logged to database!');
      setTimeout(() => setSaveSuccess(''), 4000);
    } catch (err) {
      console.error('Save error:', err);
      alert('Failed to save to database: ' + (err.response?.data?.message || err.message));
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl lg:text-2xl font-bold text-white tracking-tight">Image & Video Compliance Inspector</h1>
          <p className="text-xs text-slate-400 mt-1">Upload photos or video recordings for automated PPE validation</p>
        </div>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-xl bg-red-950/40 border border-red-800 text-red-200 text-xs flex items-center gap-2.5">
          <AlertTriangle className="w-4 h-4 text-red-400 flex-shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {saveSuccess && (
        <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-800 text-emerald-300 text-xs flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{saveSuccess}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Upload & Preview (2 cols) */}
        <div className="lg:col-span-2 space-y-4">
          {/* Dropzone / Media Viewer */}
          {!filePreview ? (
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-slate-700 hover:border-sky-500 rounded-2xl bg-slate-900/60 p-12 text-center cursor-pointer transition flex flex-col items-center justify-center min-h-[360px]"
            >
              <div className="w-16 h-16 rounded-2xl bg-slate-800 border border-slate-700 flex items-center justify-center text-sky-400 mb-4 shadow-xl">
                <UploadCloud className="w-8 h-8" />
              </div>
              <h3 className="text-base font-bold text-white mb-1">Upload Photo or Video Recording</h3>
              <p className="text-xs text-slate-400 max-w-sm mb-4">
                Drag and drop your media files here, or click to browse. Supports JPG, PNG, and MP4 (up to 50MB).
              </p>
              <span className="px-4 py-2 rounded-lg bg-slate-800 text-slate-200 hover:bg-slate-700 text-xs font-semibold border border-slate-700 transition">
                Browse Files
              </span>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*,video/*"
                onChange={handleFileChange}
                className="hidden"
              />
            </div>
          ) : (
            <div className="relative rounded-2xl bg-slate-950 border border-slate-800 overflow-hidden shadow-2xl">
              <button
                onClick={clearFile}
                className="absolute top-4 right-4 z-10 p-2 rounded-lg bg-slate-900/80 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-700 backdrop-blur-md transition"
                title="Remove file"
              >
                <X className="w-4 h-4" />
              </button>

              <div className="aspect-video flex items-center justify-center bg-black/40">
                {fileType === 'image' ? (
                  <img
                    src={detectionResult?.annotatedImage || filePreview}
                    alt="Preview"
                    className="w-full h-full object-contain"
                  />
                ) : (
                  <video
                    src={filePreview}
                    controls
                    className="w-full h-full object-contain"
                  />
                )}
              </div>

              {/* Progress bar */}
              {isProcessing && (
                <div className="p-4 bg-slate-900 border-t border-slate-800 space-y-2">
                  <div className="flex justify-between text-xs text-slate-300">
                    <span className="flex items-center gap-2">
                      <RefreshCw className="w-3.5 h-3.5 animate-spin text-sky-400" />
                      Running YOLO PPE Neural Network...
                    </span>
                    <span className="font-mono text-sky-400 font-bold">{progressPercent}%</span>
                  </div>
                  <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                    <div
                      className="bg-sky-500 h-full rounded-full transition-all duration-300"
                      style={{ width: `${progressPercent}%` }}
                    ></div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Action buttons */}
          {file && (
            <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-3">
                {fileType === 'image' ? (
                  <FileImage className="w-5 h-5 text-sky-400" />
                ) : (
                  <Film className="w-5 h-5 text-amber-400" />
                )}
                <div>
                  <div className="text-xs font-semibold text-slate-200 truncate max-w-xs">{file.name}</div>
                  <div className="text-[10px] text-slate-400">{(file.size / (1024 * 1024)).toFixed(2)} MB</div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={runDetection}
                  disabled={isProcessing}
                  className="px-5 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs shadow-lg shadow-sky-600/30 flex items-center gap-2 transition disabled:opacity-50"
                >
                  <Play className="w-4 h-4" />
                  {isProcessing ? 'Analyzing...' : 'Execute PPE Detection'}
                </button>

                {detectionResult && (
                  <button
                    onClick={saveEventToDB}
                    className="px-4 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-emerald-400 font-semibold text-xs border border-slate-700 flex items-center gap-1.5 transition"
                  >
                    <Save className="w-4 h-4" /> Save Result
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Zone selection & Compliance Summary */}
        <div className="space-y-4">
          {/* Target Zone */}
          <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-4">
            <div className="flex items-center gap-2 text-white font-bold text-xs uppercase tracking-wider border-b border-slate-800 pb-3">
              <Layers className="w-4 h-4 text-sky-400" />
              Target Compliance Zone
            </div>
            <div>
              <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
                Zone Rules
              </label>
              <select
                value={selectedZoneId}
                onChange={(e) => setSelectedZoneId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-sky-500"
              >
                {zones.map((z) => (
                  <option key={z._id} value={z._id}>
                    {z.name} ({z.code || 'ZONE'})
                  </option>
                ))}
              </select>
            </div>
            {selectedZone && (
              <div>
                <span className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Enforced PPE Gear
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {selectedZone.requiredPPE?.map((item, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-1 rounded-md bg-slate-800 text-sky-300 text-[11px] font-medium border border-slate-700 uppercase"
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Compliance Verdict Card */}
          {detectionResult ? (
            <div className="p-5 rounded-xl bg-slate-900 border border-slate-800 space-y-4 animate-in fade-in">
              <div className="border-b border-slate-800 pb-3">
                <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block mb-2">
                  Compliance Assessment
                </span>
                <div className="flex items-center gap-3">
                  {detectionResult.complianceStatus === 'COMPLIANT' && (
                    <div className="w-10 h-10 rounded-xl bg-emerald-950/60 border border-emerald-800 text-emerald-400 flex items-center justify-center">
                      <ShieldCheck className="w-6 h-6" />
                    </div>
                  )}
                  {detectionResult.complianceStatus === 'VIOLATION' && (
                    <div className="w-10 h-10 rounded-xl bg-rose-950/60 border border-rose-800 text-rose-400 flex items-center justify-center">
                      <ShieldAlert className="w-6 h-6" />
                    </div>
                  )}
                  {detectionResult.complianceStatus === 'UNCERTAIN' && (
                    <div className="w-10 h-10 rounded-xl bg-amber-950/60 border border-amber-800 text-amber-400 flex items-center justify-center">
                      <HelpCircle className="w-6 h-6" />
                    </div>
                  )}
                  <div>
                    <h3 className={`text-base font-extrabold uppercase tracking-wide ${
                      detectionResult.complianceStatus === 'COMPLIANT' ? 'text-emerald-400' :
                      detectionResult.complianceStatus === 'VIOLATION' ? 'text-rose-400' : 'text-amber-400'
                    }`}>
                      {detectionResult.complianceStatus}
                    </h3>
                    <p className="text-[11px] text-slate-400">
                      {detectionResult.complianceStatus === 'COMPLIANT'
                        ? 'All mandatory PPE gear verified.'
                        : 'Safety breach detected!'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Missing PPE */}
              {detectionResult.missingPPE?.length > 0 && (
                <div>
                  <span className="text-[11px] font-semibold text-rose-400 uppercase tracking-wider block mb-1.5">
                    Missing Equipment
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {detectionResult.missingPPE.map((ppe, i) => (
                      <span
                        key={i}
                        className="px-2.5 py-1 rounded bg-rose-950/60 text-rose-300 border border-rose-800 text-[11px] font-bold uppercase"
                      >
                        {ppe}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Detected classes */}
              <div>
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1.5">
                  Detected Gear & Objects
                </span>
                {detectionResult.detectedClasses?.length === 0 ? (
                  <p className="text-xs text-slate-500">None detected</p>
                ) : (
                  <div className="space-y-1.5">
                    {detectionResult.detectedClasses.map((item, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between p-2 rounded-lg bg-slate-950 border border-slate-800 text-xs"
                      >
                        <span className="capitalize text-slate-200">{item.name || item.class}</span>
                        <span className="font-mono text-emerald-400 font-bold">
                          {Math.round((item.confidence || 0.85) * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Video stats if video */}
              {videoFramesResult && (
                <div className="pt-3 border-t border-slate-800 text-xs text-slate-400 space-y-1">
                  <div className="flex justify-between">
                    <span>Frames Analyzed:</span>
                    <span className="font-bold text-white">{videoFramesResult.total_frames_processed}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Violation Incidents:</span>
                    <span className="font-bold text-rose-400">{videoFramesResult.total_violations_found}</span>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="p-8 rounded-xl bg-slate-900 border border-slate-800 text-center text-slate-500 text-xs">
              Upload a file and click "Execute PPE Detection" to inspect compliance.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
