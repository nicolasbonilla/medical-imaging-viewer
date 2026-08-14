import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Search, Download, Loader2, CheckCircle2,
  AlertCircle, Plus, Trash2, Wifi, WifiOff, ChevronDown, ChevronRight,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import AppHeader from '@/components/AppHeader';
import { dicomwebAPI } from '@/api/dicomweb';
import type {
  PACSConnection, PACSConnectionCreate,
  DICOMwebStudyResult, DICOMwebSeriesResult, DICOMwebImportJob,
} from '@/types';

export default function PACSBrowserPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Connection state
  const [showAddConn, setShowAddConn] = useState(false);
  const [selectedConnId, setSelectedConnId] = useState<string>('');

  // Search state
  const [searchPatientName, setSearchPatientName] = useState('');
  const [searchPatientId, setSearchPatientId] = useState('');
  const [searchModality, setSearchModality] = useState('MR');
  const [studyResults, setStudyResults] = useState<DICOMwebStudyResult[]>([]);
  const [expandedStudy, setExpandedStudy] = useState<string | null>(null);
  const [seriesResults, setSeriesResults] = useState<Record<string, DICOMwebSeriesResult[]>>({});
  const [searching, setSearching] = useState(false);

  // Import state
  const [importJobs, setImportJobs] = useState<Record<string, DICOMwebImportJob>>({});

  // Fetch connections
  const { data: connections = [] } = useQuery({
    queryKey: ['pacs-connections'],
    queryFn: dicomwebAPI.listConnections,
  });

  // Add connection
  const addConnMutation = useMutation({
    mutationFn: (data: PACSConnectionCreate) => dicomwebAPI.createConnection(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pacs-connections'] });
      setShowAddConn(false);
      toast.success('PACS connection saved');
    },
    onError: (err: any) => toast.error(err?.response?.data?.detail || 'Failed to save connection'),
  });

  // Test connection
  const testConnMutation = useMutation({
    mutationFn: (id: string) => dicomwebAPI.testConnection(id),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['pacs-connections'] });
      if (result.success) toast.success('Connection successful');
      else toast.error(`Connection failed: ${result.message}`);
    },
  });

  // Search studies
  const handleSearch = useCallback(async () => {
    if (!selectedConnId) { toast.error('Select a PACS connection first'); return; }
    setSearching(true);
    try {
      const results = await dicomwebAPI.searchStudies({
        connection_id: selectedConnId,
        patient_name: searchPatientName || undefined,
        patient_id: searchPatientId || undefined,
        modality: searchModality || undefined,
        limit: 50,
      });
      setStudyResults(results);
      if (results.length === 0) toast('No studies found');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Search failed');
    } finally {
      setSearching(false);
    }
  }, [selectedConnId, searchPatientName, searchPatientId, searchModality]);

  // Load series for a study
  const handleExpandStudy = useCallback(async (studyUid: string) => {
    if (expandedStudy === studyUid) { setExpandedStudy(null); return; }
    setExpandedStudy(studyUid);
    if (seriesResults[studyUid]) return;
    try {
      const series = await dicomwebAPI.searchSeries(selectedConnId, studyUid);
      setSeriesResults(prev => ({ ...prev, [studyUid]: series }));
    } catch (err: any) {
      toast.error('Failed to load series');
    }
  }, [selectedConnId, expandedStudy, seriesResults]);

  // Import a series
  const handleImport = useCallback(async (studyUid: string, seriesUid: string, patientId: string) => {
    try {
      const { job_id } = await dicomwebAPI.startImport({
        connection_id: selectedConnId,
        study_instance_uid: studyUid,
        series_instance_uid: seriesUid,
        patient_id: patientId,
      });
      toast.success('Import started');

      // Poll for status
      const poll = setInterval(async () => {
        const status = await dicomwebAPI.getImportStatus(job_id);
        setImportJobs(prev => ({ ...prev, [job_id]: status }));
        if (status.status === 'completed') {
          clearInterval(poll);
          toast.success('Import completed successfully');
        } else if (status.status === 'failed') {
          clearInterval(poll);
          toast.error(`Import failed: ${status.error_message}`);
        }
      }, 2000);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Import failed');
    }
  }, [selectedConnId]);

  return (
    <div className="min-h-screen" style={{ background: '#030712' }}>
      {/* Header — unified app bar (Design System v2.0) */}
      <AppHeader
        title={t('pacs.title', 'PACS Browser')}
        subtitle={t('pacs.subtitle', 'DICOMweb Integration')}
        breadcrumbs={[
          { label: t('nav.home', 'Home'), path: '/app' },
          { label: t('pacs.title', 'PACS Browser') },
        ]}
        onBack={() => navigate(-1)}
      />

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Connection Selector */}
        <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">PACS Connection</h2>
            <button
              onClick={() => setShowAddConn(!showAddConn)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500/20 hover:bg-blue-500/30 text-blue-400 rounded-lg text-xs font-medium transition-colors"
            >
              <Plus className="w-3 h-3" /> Add Connection
            </button>
          </div>

          {showAddConn && (
            <AddConnectionForm
              onSubmit={(data) => addConnMutation.mutate(data)}
              onCancel={() => setShowAddConn(false)}
              loading={addConnMutation.isPending}
            />
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {connections.map((conn) => (
              <button
                key={conn.id}
                onClick={() => setSelectedConnId(conn.id)}
                className={`p-3 rounded-xl text-left transition-all ${
                  selectedConnId === conn.id
                    ? 'ring-2 ring-blue-500 bg-blue-500/10'
                    : 'bg-white/5 hover:bg-white/10'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-white">{conn.name}</span>
                  {conn.is_reachable === true && <Wifi className="w-3 h-3 text-green-400" />}
                  {conn.is_reachable === false && <WifiOff className="w-3 h-3 text-red-400" />}
                </div>
                <p className="text-[10px] text-gray-500 mt-1 truncate">{conn.base_url}</p>
                <div className="flex gap-2 mt-2">
                  <button
                    onClick={(e) => { e.stopPropagation(); testConnMutation.mutate(conn.id); }}
                    className="text-[10px] text-blue-400 hover:text-blue-300"
                  >
                    Test
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); dicomwebAPI.deleteConnection(conn.id).then(() => queryClient.invalidateQueries({ queryKey: ['pacs-connections'] })); }}
                    className="text-[10px] text-red-400 hover:text-red-300"
                  >
                    Delete
                  </button>
                </div>
              </button>
            ))}
            {connections.length === 0 && !showAddConn && (
              <p className="text-sm text-gray-500 col-span-full text-center py-4">No PACS connections configured. Click "Add Connection" to get started.</p>
            )}
          </div>
        </div>

        {/* Search */}
        {selectedConnId && (
          <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
              <Search className="w-4 h-4 inline mr-2" />Study Search (QIDO-RS)
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 mb-4">
              <input
                value={searchPatientName}
                onChange={(e) => setSearchPatientName(e.target.value)}
                placeholder="Patient Name"
                className="px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-gray-500"
              />
              <input
                value={searchPatientId}
                onChange={(e) => setSearchPatientId(e.target.value)}
                placeholder="Patient ID"
                className="px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-gray-500"
              />
              <select
                value={searchModality}
                onChange={(e) => setSearchModality(e.target.value)}
                className="px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white"
              >
                <option value="MR">MR</option>
                <option value="CT">CT</option>
                <option value="">Any</option>
              </select>
              <button
                onClick={handleSearch}
                disabled={searching}
                className="flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-lg text-sm text-white font-medium transition-colors"
              >
                {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                Search PACS
              </button>
            </div>

            {/* Results */}
            {studyResults.length > 0 && (
              <div className="space-y-2">
                {studyResults.map((study) => (
                  <div key={study.study_instance_uid} className="bg-white/5 rounded-xl overflow-hidden">
                    <button
                      onClick={() => handleExpandStudy(study.study_instance_uid)}
                      className="w-full p-3 text-left flex items-center gap-3 hover:bg-white/5 transition-colors"
                    >
                      {expandedStudy === study.study_instance_uid
                        ? <ChevronDown className="w-4 h-4 text-blue-400" />
                        : <ChevronRight className="w-4 h-4 text-gray-500" />
                      }
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3">
                          <span className="text-sm font-medium text-white">{study.patient_name || 'Unknown'}</span>
                          <span className="text-xs text-gray-500">{study.patient_id}</span>
                          <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded text-[10px] font-medium">{study.modality}</span>
                        </div>
                        <p className="text-xs text-gray-400 mt-0.5 truncate">
                          {study.study_date} — {study.study_description || 'No description'}
                        </p>
                      </div>
                      <span className="text-xs text-gray-500">{study.number_of_series} series</span>
                    </button>

                    {expandedStudy === study.study_instance_uid && (
                      <div className="px-3 pb-3 pl-10 space-y-1.5">
                        {(seriesResults[study.study_instance_uid] || []).map((series) => (
                          <div key={series.series_instance_uid} className="flex items-center justify-between p-2 bg-white/5 rounded-lg">
                            <div>
                              <span className="text-xs text-white font-medium">
                                Series {series.series_number}: {series.series_description || series.modality}
                              </span>
                              <span className="text-[10px] text-gray-500 ml-2">{series.number_of_instances} instances</span>
                            </div>
                            <button
                              onClick={() => {
                                const patientId = prompt('Enter MSTool-AI Patient ID to import into:');
                                if (patientId) handleImport(study.study_instance_uid, series.series_instance_uid, patientId);
                              }}
                              className="flex items-center gap-1 px-2 py-1 bg-green-600/20 hover:bg-green-600/30 text-green-400 rounded text-xs font-medium transition-colors"
                            >
                              <Download className="w-3 h-3" /> Import
                            </button>
                          </div>
                        ))}
                        {!seriesResults[study.study_instance_uid] && (
                          <div className="flex items-center gap-2 text-gray-500 text-xs py-2">
                            <Loader2 className="w-3 h-3 animate-spin" /> Loading series...
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Active Imports */}
        {Object.keys(importJobs).length > 0 && (
          <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Import Jobs</h2>
            <div className="space-y-2">
              {Object.values(importJobs).map((job) => (
                <div key={job.job_id} className="flex items-center gap-3 p-3 bg-white/5 rounded-lg">
                  {job.status === 'completed' ? <CheckCircle2 className="w-4 h-4 text-green-400" /> :
                   job.status === 'failed' ? <AlertCircle className="w-4 h-4 text-red-400" /> :
                   <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />}
                  <div className="flex-1">
                    <span className="text-xs text-white font-medium capitalize">{job.status}</span>
                    {job.error_message && <p className="text-[10px] text-red-400">{job.error_message}</p>}
                  </div>
                  <div className="w-24 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 transition-all" style={{ width: `${job.progress_percent}%` }} />
                  </div>
                  <span className="text-[10px] text-gray-500">{job.progress_percent}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function AddConnectionForm({ onSubmit, onCancel, loading }: {
  onSubmit: (data: PACSConnectionCreate) => void;
  onCancel: () => void;
  loading: boolean;
}) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [authType, setAuthType] = useState<'none' | 'basic' | 'bearer'>('none');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  return (
    <div className="mb-4 p-4 bg-white/5 rounded-xl space-y-3">
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Connection Name (e.g. Hospital PACS)"
        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-gray-500" />
      <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="DICOMweb Base URL (e.g. https://pacs.hospital.org/dicom-web)"
        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-gray-500" />
      <select value={authType} onChange={(e) => setAuthType(e.target.value as any)}
        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white">
        <option value="none">No Authentication</option>
        <option value="basic">Basic Auth</option>
        <option value="bearer">Bearer Token</option>
      </select>
      {authType === 'basic' && (
        <div className="grid grid-cols-2 gap-2">
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username"
            className="px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-gray-500" />
          <input value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" type="password"
            className="px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-gray-500" />
        </div>
      )}
      <div className="flex gap-2">
        <button
          onClick={() => onSubmit({ name, base_url: url, auth_type: authType, username: username || undefined, password: password || undefined, verify_ssl: true })}
          disabled={!name || !url || loading}
          className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 rounded-lg text-sm text-white font-medium transition-colors"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : 'Save Connection'}
        </button>
        <button onClick={onCancel} className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-sm text-gray-300 transition-colors">
          Cancel
        </button>
      </div>
    </div>
  );
}
