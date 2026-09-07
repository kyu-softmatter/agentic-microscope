function plugflow_fluctuations_passive_moduli_passivecal
% Plug flow microrheology — two-bead version.
% Input files have 4 columns (with header): Left_x  Left_y  Right_x  Right_y
% All moduli are computed independently for the LEFT and RIGHT bead,
% then plotted together on the same axes.
%
% Trap calibration is obtained from passive files at each power using
% the MSD plateau:
%   MSD_inf = 2*kT/kappa   =>   kappa = 2*kT / MSD_inf

clear; clc; close all;

%% ================= USER SETTINGS =================
px_to_um   = 0.065;
frame_time = 0.020407;
fs         = 1/frame_time;

a_um       = 2.5;
nfft       = 1024;
freq_limit = 20;

kT_um = 4.045e-3;   % pN*um

fluct_method = 'kk';   % 'kk' | 'tassieri' | 'mason'

kk_smooth_span_hz = 0.1;
kk_psd_halve      = true;

plot_kk_psd_debug = false;
exposure_time_s   = 0.020407;
exposure_floor    = 0.4;

beta_oversample   = 1000;
taper_frac        = 0.25;
qlog_base         = 1.45;
max_tau_seconds   = inf;

mason_win         = 7;
mason_alpha_clamp = [0, 1];
mason_use_3D      = false;

mean_method          = 'linear';
moving_window_sec    = 2.0;

use_full_length_for_plug = false;

plot_each_file    = false;
plot_speed_median = true;
plot_power_median = true;

overlay_passive_if_present = true;

make_master_speed_plot = true;
master_speeds_to_show  = [1, 2, 3, 4, 5, 6];
master_speed_tol       = 1e-3;

f_master     = linspace(0.05, freq_limit, 250).';
omega_master = 2*builtin('pi')*f_master;

use_bulk_rheology   = false;
plot_bulk_rheology  = false;
bulk_file           = '20260131_80%bf_WATER_GLYC_FreqSweep_5%_2.csv';
bulk_omega_min_plot = 5;

kB       = 1.380649e-23;
T_kelvin = 298;

%% ======== Trap calibration from passive MSD plateau ========
Ptol = 5e-4;                 % power matching tolerance
msd_plateau_frac = 0.20;     % use last 20% of MSD points
msd_min_points   = 50;       % minimum number of plateau points
use_axis_mean_for_kappa = true;  % average x/y plateau to get one kappa per bead/file

%% ======== LOAD BULK (optional) ========
if use_bulk_rheology
    bulk = readmatrix(bulk_file);
    Gp_bulk    = bulk(:,1);
    Gpp_bulk   = bulk(:,2);
    omega_bulk = bulk(:,4);
    ok = isfinite(Gp_bulk) & isfinite(Gpp_bulk) & isfinite(omega_bulk) & omega_bulk > 0;
    Gp_bulk    = Gp_bulk(ok);
    Gpp_bulk   = Gpp_bulk(ok);
    omega_bulk = omega_bulk(ok);
    bulk_mask       = omega_bulk >= bulk_omega_min_plot;
    omega_bulk_plot = omega_bulk(bulk_mask);
    Gp_bulk_plot    = Gp_bulk(bulk_mask);
    Gpp_bulk_plot   = Gpp_bulk(bulk_mask);
end

%% ================= LOAD FILES =================
files = dir('*.txt');
if isempty(files), error('No .txt files found.'); end
names = {files.name};
names = names(:);

is_passive = contains(lower(names), 'passive');
is_plug    = contains(lower(names), 'creepx_');

%% ================= PARSE METADATA =================
plugMeta = struct('name',{},'power',[],'speed',[],'ok',[]);
k = 0;
for i = 1:numel(names)
    if ~is_plug(i) || is_passive(i), continue; end
    fn = names{i};
    tokV = regexp(fn,'creepx_(\d*\.?\d+)umps_','tokens','once');
    tokP = regexp(fn,'_(\d*\.?\d+)_OT(\d*\.?\d+)','tokens','once');
    if isempty(tokV) || isempty(tokP), continue; end
    k = k + 1;
    plugMeta(k).name  = fn;
    plugMeta(k).speed = str2double(tokV{1});
    plugMeta(k).power = str2double(tokP{1}) * str2double(tokP{2});
    plugMeta(k).ok    = true;
end

passMeta = struct('name',{},'power',[],'ok',[]);
k = 0;
for i = 1:numel(names)
    if ~is_passive(i), continue; end
    fn = names{i};
    tokP = regexp(fn,'_(\d*\.?\d+)_OT(\d*\.?\d+)','tokens','once');
    if isempty(tokP), continue; end
    k = k + 1;
    passMeta(k).name  = fn;
    passMeta(k).power = str2double(tokP{1}) * str2double(tokP{2});
    passMeta(k).ok    = true;
end

if isempty(plugMeta)
    error('No plug (creepx_) files found with expected naming patterns.');
end

uniqP = unique(vertcat(plugMeta.power));
fprintf('Plug powers detected: %s\n', mat2str(uniqP.',4));
fprintf('Mean subtraction method: %s\n', mean_method);
fprintf('Fluctuation extraction method: %s\n', fluct_method);

pi_const = builtin('pi'); %#ok<NASGU>

%% ================= BEAD LABELS =================
bead_labels = {'Left','Right'};
bead_cols   = [1,3];   % column indices in the 4-col data file (x only)

%% ================= PASSIVE-BASED TRAP CALIBRATION =================
passiveCal = struct('power',{},'kappa_left',{},'kappa_right',{}, ...
                    'msd_plateau_left',{},'msd_plateau_right',{}, ...
                    'files',{},'nfiles',{});

if ~isempty(passMeta)
    uniqPassP = unique(vertcat(passMeta.power));

    for ip = 1:numel(uniqPassP)
        Ppass = uniqPassP(ip);
        idxs  = find(abs(vertcat(passMeta.power) - Ppass) < Ptol);
        filesP = {passMeta(idxs).name};

        [kL, msdL] = calibrate_kappa_from_passive_files(filesP, px_to_um, 1, ...
                            msd_plateau_frac, msd_min_points, kT_um, use_axis_mean_for_kappa);
        [kR, msdR] = calibrate_kappa_from_passive_files(filesP, px_to_um, 3, ...
                            msd_plateau_frac, msd_min_points, kT_um, use_axis_mean_for_kappa);

        passiveCal(end+1).power             = Ppass; %#ok<AGROW>
        passiveCal(end).kappa_left          = kL;
        passiveCal(end).kappa_right         = kR;
        passiveCal(end).msd_plateau_left    = msdL;
        passiveCal(end).msd_plateau_right   = msdR;
        passiveCal(end).files               = filesP;
        passiveCal(end).nfiles              = numel(filesP);

        fprintf(['Passive calibration: P=%.4g | MSDplat_L=%.4g um^2 | ' ...
                 'MSDplat_R=%.4g um^2 | kappa_L=%.4g pN/um | kappa_R=%.4g pN/um\n'], ...
                 Ppass, msdL, msdR, kL, kR);
    end
else
    warning('No passive files found. Cannot perform passive-based trap calibration.');
end

%% ================= MASTER ACCUMULATORS =================
for b = 1:2
    master(b).omega         = omega_master(:); %#ok<AGROW>
    master(b).V_list        = [];
    master(b).Gp_cols       = {};
    master(b).Gpp_cols      = {};
    master(b).Gp_pass_cols  = [];
    master(b).Gpp_pass_cols = [];
end

%% ================= LOOP OVER POWER =================
for ipow = 1:numel(uniqP)
    P = uniqP(ipow);

    idxCal = find(abs([passiveCal.power] - P) < Ptol, 1);
    if isempty(idxCal)
        warning('No passive-based calibration for Power=%.6g. Skipping.', P);
        continue;
    end

    kappa_bead = [passiveCal(idxCal).kappa_left, passiveCal(idxCal).kappa_right];

    %% ---- Per-power figure: 2 rows (Left / Right), shared axes ----
    fig_pow = figure('Name', sprintf('Power=%.4g  method=%s', P, fluct_method), ...
                     'Position', [50 50 900 700]);
    ax_pow = gobjects(2,1);
    for b = 1:2
        ax_pow(b) = subplot(2,1,b);
        hold(ax_pow(b),'on');
        grid(ax_pow(b),'on');
        set(ax_pow(b),'XScale','log','YScale','log','FontSize',11);
        xlabel(ax_pow(b),'\omega (rad/s)');
        ylabel(ax_pow(b),'G'', G'''' (Pa)');
        title(ax_pow(b), sprintf('%s bead | P=%.4g kappa=%.3g', bead_labels{b}, P, kappa_bead(b)));
    end

    %% ---- Passive (both beads) ----
    have_passive = [false, false]; %#ok<NASGU>
    omega_pass  = cell(2,1); %#ok<NASGU>
    Gp_pass     = cell(2,1); %#ok<NASGU>
    Gpp_pass    = cell(2,1); %#ok<NASGU>

    if overlay_passive_if_present && ~isempty(passMeta)
        idxs = find(abs(vertcat(passMeta.power) - P) < 1e-12);
        if ~isempty(idxs)
            filesP = {passMeta(idxs).name};
            for b = 1:2
                [op, Gfl] = extract_moduli_from_filelist( ...
                    filesP, px_to_um, frame_time, fs, nfft, freq_limit, ...
                    kT_um, a_um, kappa_bead(b), ...
                    fluct_method, kk_smooth_span_hz, kk_psd_halve, ...
                    beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
                    mason_win, mason_alpha_clamp, mason_use_3D, ...
                    true, 'none', moving_window_sec, ...
                    plot_kk_psd_debug, exposure_time_s, exposure_floor, ...
                    sprintf('PASSIVE P=%.4g %s', P, bead_labels{b}), ...
                    bead_cols(b));

                have_passive(b) = true;
                omega_pass{b}   = op;
                Gp_pass{b}      = real(Gfl);
                Gpp_pass{b}     = imag(Gfl);

                loglog(ax_pow(b), op, abs(real(Gfl)),  'k-',  'LineWidth',2.0, ...
                       'DisplayName', sprintf('Passive G'' (%s)', fluct_method));
                loglog(ax_pow(b), op, abs(imag(Gfl)), 'k--', 'LineWidth',2.0, ...
                       'DisplayName', sprintf('Passive G'''' (%s)', fluct_method));

                if make_master_speed_plot
                    master(b).Gp_pass_cols(:,end+1)  = interp_signed_log(op, real(Gfl), master(b).omega);
                    master(b).Gpp_pass_cols(:,end+1) = interp_signed_log(op, imag(Gfl), master(b).omega);
                end
            end
        end
    end

    %% ---- Plug files grouped by speed ----
    pplug = vertcat(plugMeta.power);
    vplug = vertcat(plugMeta.speed);
    idxP  = find(abs(pplug - P) < 1e-12);
    speeds = unique(vplug(idxP));

    speedCurves = struct('speed',{},'omega',{},'Gp_med',{},'Gpp_med',{},'Gp_files',{},'Gpp_files',{});

    for si = 1:numel(speeds)
        V       = speeds(si);
        idxPV   = idxP(abs(vplug(idxP) - V) < 1e-12);
        filesPV = {plugMeta(idxPV).name};

        for b = 1:2
            [omega_b, Gp_b, Gpp_b] = extract_moduli_from_plug_files_per_file( ...
                filesPV, px_to_um, frame_time, fs, nfft, freq_limit, ...
                kT_um, a_um, kappa_bead(b), ...
                fluct_method, kk_smooth_span_hz, kk_psd_halve, ...
                beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
                mason_win, mason_alpha_clamp, mason_use_3D, ...
                use_full_length_for_plug, mean_method, moving_window_sec, ...
                plot_kk_psd_debug, exposure_time_s, exposure_floor, ...
                sprintf('PLUG P=%.4g V=%.3g %s', P, V, bead_labels{b}), ...
                bead_cols(b));

            sc_idx = (si-1)*2 + b;
            speedCurves(sc_idx).speed     = V;
            speedCurves(sc_idx).bead      = b;
            speedCurves(sc_idx).omega     = omega_b;
            speedCurves(sc_idx).Gp_files  = Gp_b;
            speedCurves(sc_idx).Gpp_files = Gpp_b;
            speedCurves(sc_idx).Gp_med    = signed_log_median(Gp_b);
            speedCurves(sc_idx).Gpp_med   = signed_log_median(Gpp_b);

            if plot_each_file
                for jj = 1:size(Gp_b,2)
                    loglog(ax_pow(b), w, abs(Gp_b(:,jj)),  '-',  'LineWidth',0.6, 'HandleVisibility','off');
                    loglog(ax_pow(b), w, abs(Gpp_b(:,jj)), '--', 'LineWidth',0.6, 'HandleVisibility','off');
                end
            end

            w = omega_b;
            if plot_speed_median
                loglog(ax_pow(b), w, abs(speedCurves(sc_idx).Gp_med),  '-',  'LineWidth',1.8, ...
                       'DisplayName', sprintf('V=%.3g G''',  V));
                loglog(ax_pow(b), w, abs(speedCurves(sc_idx).Gpp_med), '--', 'LineWidth',1.8, ...
                       'DisplayName', sprintf('V=%.3g G''''', V));
            end

            if make_master_speed_plot
                if isempty(master_speeds_to_show) || any(abs(master_speeds_to_show - V) < master_speed_tol)
                    Gp_interp  = interp_cols_signed_log(omega_b, Gp_b,  master(b).omega);
                    Gpp_interp = interp_cols_signed_log(omega_b, Gpp_b, master(b).omega);
                    idxV = find(abs(master(b).V_list - V) < master_speed_tol, 1);
                    if isempty(idxV)
                        master(b).V_list(end+1,1) = V;
                        master(b).Gp_cols{end+1}  = Gp_interp;
                        master(b).Gpp_cols{end+1} = Gpp_interp;
                    else
                        master(b).Gp_cols{idxV}  = [master(b).Gp_cols{idxV},  Gp_interp];
                        master(b).Gpp_cols{idxV} = [master(b).Gpp_cols{idxV}, Gpp_interp];
                    end
                end
            end
        end
    end

    for b = 1:2
        sc_b = speedCurves([speedCurves.bead] == b);
        if plot_power_median && numel(sc_b) >= 2
            w_com   = sc_b(1).omega;
            Gp_mat  = nan(numel(w_com), numel(sc_b));
            Gpp_mat = nan(numel(w_com), numel(sc_b));
            for si = 1:numel(sc_b)
                Gp_mat(:,si)  = interp1(log(sc_b(si).omega), log(abs(sc_b(si).Gp_med)+eps),  log(w_com), 'linear','extrap');
                Gpp_mat(:,si) = interp1(log(sc_b(si).omega), log(abs(sc_b(si).Gpp_med)+eps), log(w_com), 'linear','extrap');
            end
            loglog(ax_pow(b), w_com, exp(median(Gp_mat,2,'omitnan')),  'r-',  'LineWidth',2.5, 'DisplayName','median(speeds) G''');
            loglog(ax_pow(b), w_com, exp(median(Gpp_mat,2,'omitnan')), 'r--', 'LineWidth',2.5, 'DisplayName','median(speeds) G''''');
        end

        if use_bulk_rheology && plot_bulk_rheology
            loglog(ax_pow(b), omega_bulk_plot, Gp_bulk_plot,  'kd','MarkerFaceColor','k',   'MarkerSize',5,'DisplayName','Bulk G''');
            loglog(ax_pow(b), omega_bulk_plot, Gpp_bulk_plot, 'ks','MarkerFaceColor','none','MarkerSize',5,'DisplayName','Bulk G''''');
        end

        legend(ax_pow(b), 'Location','best');
    end

    sgtitle(fig_pow, sprintf(['P=%.4g  |  kappa_L=%.3g pN/um  |  ' ...
            'kappa_R=%.3g pN/um  |  mean=%s  |  method=%s'], ...
            P, kappa_bead(1), kappa_bead(2), mean_method, fluct_method), ...
            'FontSize', 12);
end

%% ================= MASTER PLOT =================
if make_master_speed_plot
    fig_master = figure('Name', 'MASTER – pooled across all powers', ...
                        'Position', [80 80 1000 750]);

    for b = 1:2
        ax_m = subplot(2,1,b);
        hold(ax_m,'on'); grid(ax_m,'on');
        set(ax_m,'XScale','log','YScale','log','FontSize',12);
        xlabel(ax_m,'\omega (rad/s)');
        ylabel(ax_m,'G'', G'''' (Pa)');
        title(ax_m, sprintf('MASTER – %s bead (method=%s)', bead_labels{b}, fluct_method));

        if ~isempty(master(b).Gp_pass_cols)
            Gp_pm  = signed_log_median(master(b).Gp_pass_cols);
            Gpp_pm = signed_log_median(master(b).Gpp_pass_cols);
            loglog(ax_m, master(b).omega, abs(Gp_pm),  'k-',  'LineWidth',3.0, ...
                   'DisplayName', sprintf('Wi=0 G'' (%s)', upper(fluct_method)));
            loglog(ax_m, master(b).omega, abs(Gpp_pm), 'k--', 'LineWidth',3.0, ...
                   'DisplayName', sprintf('Wi=0 G'''' (%s)', upper(fluct_method)));
        end

        V_used  = master(b).V_list(:);
        Wi_used = 1.1 .* V_used;
        if ~isempty(Wi_used)
            [Wi_sort, ord] = sort(Wi_used);
            Gp_cells  = master(b).Gp_cols(ord);
            Gpp_cells = master(b).Gpp_cols(ord);

            base_cmap = turbo(256);
            cmap = base_cmap(50:256,:);
            vmin = min(Wi_sort);
            vmax = max(Wi_sort);
            if vmax == vmin, vmax = vmin + eps; end

            for i = 1:numel(Wi_sort)
                t_c = (Wi_sort(i) - vmin) / (vmax - vmin);
                idx_c = 1 + round(t_c * (size(cmap,1)-1));
                idx_c = max(1, min(size(cmap,1), idx_c));
                c = cmap(idx_c,:);
                Gp_m  = signed_log_median(Gp_cells{i});
                Gpp_m = signed_log_median(Gpp_cells{i});
                loglog(ax_m, master(b).omega, abs(Gp_m),  '-',  'Color',c,'LineWidth',2.5, ...
                       'DisplayName', sprintf('Wi=%.3g G''',  Wi_sort(i)));
                loglog(ax_m, master(b).omega, abs(Gpp_m), '--', 'Color',c,'LineWidth',2.5, ...
                       'DisplayName', sprintf('Wi=%.3g G''''', Wi_sort(i)));
            end

            colormap(ax_m, cmap);
            caxis(ax_m, [vmin vmax]);
            cb = colorbar(ax_m);
            cb.Label.String = 'Wi';
            cb.FontSize = 11;
            cb.Label.FontSize = 13;
            cb.Ticks = Wi_sort;
            cb.TickLabels = arrayfun(@(x) sprintf('%.3g',x), Wi_sort, 'UniformOutput',false);
        end

        if use_bulk_rheology && plot_bulk_rheology
            loglog(ax_m, omega_bulk_plot, Gp_bulk_plot,  'kd','MarkerFaceColor','k',   'MarkerSize',5,'DisplayName','Bulk G''');
            loglog(ax_m, omega_bulk_plot, Gpp_bulk_plot, 'ks','MarkerFaceColor','none','MarkerSize',5,'DisplayName','Bulk G''''');
        end

        legend(ax_m,'Location','best');
    end

    sgtitle(fig_master, sprintf('MASTER – pooled all powers | method=%s', fluct_method), 'FontSize',13);
end

end % main function


%% ===================== EXTRACTION WRAPPERS =====================

function [omega, Gp_files, Gpp_files] = extract_moduli_from_plug_files_per_file( ...
    file_list, px_to_um, frame_time, fs, nfft, freq_limit, ...
    kT_um, a_um, kappa, ...
    method, kk_smooth_span_hz, kk_psd_halve, ...
    beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
    mason_win, mason_alpha_clamp, mason_use_3D, ...
    use_full_length, mean_method, moving_window_sec, ...
    plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag, bead_col)

[Xmat, t_use] = load_and_crop_stack(file_list, px_to_um, frame_time, use_full_length, bead_col);

nFiles    = size(Xmat,2);
omega     = [];
Gp_files  = [];
Gpp_files = [];

for j = 1:nFiles
    x  = Xmat(:,j);
    dx = subtract_mean_motion(x, t_use, mean_method, moving_window_sec);

    [omega_j, Gfluid_j] = extract_moduli_from_trace( ...
        dx, t_use, fs, nfft, freq_limit, kT_um, a_um, kappa, ...
        method, kk_smooth_span_hz, kk_psd_halve, ...
        beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
        mason_win, mason_alpha_clamp, mason_use_3D, ...
        plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag, j);

    if isempty(omega)
        omega     = omega_j;
        Gp_files  = nan(numel(omega), nFiles);
        Gpp_files = nan(numel(omega), nFiles);
    end
    Gp_files(:,j)  = interp1(omega_j, real(Gfluid_j), omega, 'linear','extrap');
    Gpp_files(:,j) = interp1(omega_j, imag(Gfluid_j), omega, 'linear','extrap');
end
end


function [omega, Gfluid] = extract_moduli_from_filelist( ...
    file_list, px_to_um, frame_time, fs, nfft, freq_limit, ...
    kT_um, a_um, kappa, ...
    method, kk_smooth_span_hz, kk_psd_halve, ...
    beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
    mason_win, mason_alpha_clamp, mason_use_3D, ...
    use_full_length, mean_method, moving_window_sec, ...
    plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag, bead_col)

if strcmpi(method,'kk')
    [omega, Gfluid] = kk_moduli_from_filelist( ...
        file_list, px_to_um, frame_time, fs, nfft, freq_limit, ...
        kT_um, a_um, kappa, kk_smooth_span_hz, kk_psd_halve, ...
        use_full_length, mean_method, moving_window_sec, ...
        plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag, bead_col);
    return;
end

[Xmat, t_use] = load_and_crop_stack(file_list, px_to_um, frame_time, use_full_length, bead_col);
nFiles   = size(Xmat,2);
omega    = [];
Gp_cols  = [];
Gpp_cols = [];

for j = 1:nFiles
    x = Xmat(:,j);
    if ~strcmpi(mean_method,'none')
        x = subtract_mean_motion(x, t_use, mean_method, moving_window_sec);
    end
    [omega_j, G_j] = extract_moduli_from_trace( ...
        x, t_use, fs, nfft, freq_limit, kT_um, a_um, kappa, ...
        method, kk_smooth_span_hz, kk_psd_halve, ...
        beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
        mason_win, mason_alpha_clamp, mason_use_3D, ...
        false, exposure_time_s, exposure_floor, debug_tag, j);

    if isempty(omega)
        omega    = omega_j;
        Gp_cols  = nan(numel(omega), nFiles);
        Gpp_cols = nan(numel(omega), nFiles);
    end
    Gp_cols(:,j)  = interp1(omega_j, real(G_j), omega, 'linear','extrap');
    Gpp_cols(:,j) = interp1(omega_j, imag(G_j), omega, 'linear','extrap');
end

Gfluid = signed_log_median(Gp_cols) + 1i*signed_log_median(Gpp_cols);
end


function [omega, Gfluid] = extract_moduli_from_trace( ...
    x, t, fs, nfft, freq_limit, kT_um, a_um, kappa, ...
    method, kk_smooth_span_hz, kk_psd_halve, ...
    beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
    mason_win, mason_alpha_clamp, mason_use_3D, ...
    plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag, trace_idx)

if nargin < 22, plot_kk_psd_debug = false; end
if nargin < 23 || isempty(exposure_time_s), exposure_time_s = 0.020; end
if nargin < 24 || isempty(exposure_floor),  exposure_floor  = 0.4;   end
if nargin < 25, debug_tag = 'TRACE'; end
if nargin < 26, trace_idx = 1; end

switch lower(method)
    case 'kk'
        [omega, Gfluid] = kk_moduli_from_trace(x, fs, nfft, freq_limit, kT_um, a_um, kappa, ...
            kk_smooth_span_hz, kk_psd_halve, plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag, trace_idx);
    case 'tassieri'
        [omega, Gfluid] = tassieri_moduli_from_trace(x, t, fs, nfft, freq_limit, a_um, kappa, ...
            beta_oversample, taper_frac, qlog_base, max_tau_seconds);
    case 'mason'
        [omega, Gfluid] = mason_moduli_from_trace(x, t, fs, nfft, freq_limit, kT_um, a_um, ...
            mason_win, mason_alpha_clamp, mason_use_3D);
    otherwise
        error('Unknown method "%s". Use kk|tassieri|mason.', method);
end
end


%% ===================== KK =====================

function [omega, Gfluid] = kk_moduli_from_filelist(file_list, px_to_um, frame_time, fs, nfft, freq_limit, ...
    kT_um, a_um, kappa, smooth_span_hz, kk_psd_halve, use_full_length, mean_method, moving_window_sec, ...
    plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag, bead_col)

[Xmat, t_use] = load_and_crop_stack(file_list, px_to_um, frame_time, use_full_length, bead_col);

psd_acc = [];
for j = 1:size(Xmat,2)
    x = Xmat(:,j);
    if ~strcmpi(mean_method,'none')
        x = subtract_mean_motion(x, t_use, mean_method, moving_window_sec);
    end
    x = x - mean(x,'omitnan');
    x = detrend(x,'linear');
    [Pxx, f_raw] = pwelch(x, hanning(nfft), nfft/2, nfft, fs);
    if j == 1, f = f_raw(2:end); end
    psd_acc(:,j) = Pxx(2:end); %#ok<AGROW>
end

PSD_mean = mean(psd_acc, 2, 'omitnan');
keep     = f <= freq_limit;
f        = f(keep);
PSD_mean = PSD_mean(keep);

Te       = exposure_time_s;
PSD_raw  = PSD_mean;
H2       = (sin(pi*f*Te)./(pi*f*Te)).^2;
H2(f==0) = 1;
H2_clip  = max(H2, exposure_floor);
PSD_corr = PSD_raw ./ H2_clip;
PSD_use  = PSD_corr;
if kk_psd_halve, PSD_use = PSD_use ./ 2; end

if smooth_span_hz > 0
    PSD_smooth = 10.^smooth(log10(f), log10(PSD_use), smooth_span_hz, 'rlowess');
else
    PSD_smooth = PSD_use;
end

if plot_kk_psd_debug
    figure(7001); clf;
    loglog(f, PSD_raw./2,'k.','DisplayName','Raw PSD'); hold on;
    loglog(f, PSD_corr./2,'r-','LineWidth',1.5,'DisplayName','Exposure-corrected');
    loglog(f, PSD_smooth,'b-','LineWidth',2,'DisplayName','Smoothed (used)');
    grid on; xlabel('f (Hz)'); ylabel('PSD (\mum^2/Hz)');
    title(sprintf('KK PSD debug (%s)', debug_tag));
    yyaxis right;
    semilogx(f, H2,'g--','LineWidth',1.2,'DisplayName','H2');
    semilogx(f, H2_clip,'m-','LineWidth',1.2,'DisplayName','H2 clipped');
    ylabel('|H(f)|^2'); ylim([0 1.05]); legend('Location','southwest');
end

omega  = 2*builtin('pi')*f(:);
im_chi = -(omega .* PSD_smooth) / (2 * kT_um);
re_chi = zeros(size(im_chi));
for i = 1:numel(omega)
    w0 = omega(i);
    integrand = ((omega .* im_chi) - (w0 * im_chi(i))) ./ (omega.^2 - w0^2);
    integrand(i) = 0;
    re_chi(i) = (2/pi) * trapz(omega, integrand);
end
if median(re_chi(1:min(10,end))) < 0, re_chi = -re_chi; end

chi    = re_chi + 1i*im_chi;
Gfluid = ((1 ./ chi) - kappa) ./ (6 * builtin('pi') * a_um);
end


function [omega, Gfluid] = kk_moduli_from_trace(x, fs, nfft, freq_limit, kT_um, a_um, kappa, ...
    smooth_span_hz, kk_psd_halve, plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag, trace_idx)

x = x(:) - mean(x,'omitnan');
x = detrend(x,'linear');
[Pxx, f_raw] = pwelch(x, hanning(nfft), nfft/2, nfft, fs);
f   = f_raw(2:end);
Pxx = Pxx(2:end);
keep = f <= freq_limit;
f   = f(keep);
Pxx = Pxx(keep);

Te       = exposure_time_s;
H2       = (sin(pi*f*Te)./(pi*f*Te)).^2;
H2(f==0) = 1;
H2_clip  = max(H2, exposure_floor);
PSD_corr = Pxx ./ H2_clip;
PSD_use  = PSD_corr;
if kk_psd_halve, PSD_use = PSD_use ./ 2; end

if smooth_span_hz > 0
    PSD_smooth = 10.^smooth(log10(f), log10(PSD_use+eps), smooth_span_hz, 'rlowess');
else
    PSD_smooth = PSD_use;
end

if plot_kk_psd_debug
    figure(7100+trace_idx); clf;
    loglog(f, Pxx./2,'k.','DisplayName','Raw PSD'); hold on;
    loglog(f, PSD_corr./2,'r-','LineWidth',1.5,'DisplayName','Exposure-corrected');
    loglog(f, PSD_smooth,'b-','LineWidth',2,'DisplayName','Smoothed (used)');
    grid on; xlabel('f (Hz)'); ylabel('PSD (\mum^2/Hz)');
    title(sprintf('KK PSD debug (%s) trace %d', debug_tag, trace_idx));
    yyaxis right;
    semilogx(f, H2,'g--','LineWidth',1.2,'DisplayName','H2');
    semilogx(f, H2_clip,'m-','LineWidth',1.2,'DisplayName','H2 clipped');
    ylabel('|H(f)|^2'); ylim([0 1.05]); legend('Location','southwest');
end

omega  = 2*builtin('pi')*f(:);
im_chi = -(omega .* PSD_smooth) / (2 * kT_um);
re_chi = zeros(size(im_chi));
for i = 1:numel(omega)
    w0 = omega(i);
    integrand = ((omega .* im_chi) - (w0 * im_chi(i))) ./ (omega.^2 - w0^2);
    integrand(i) = 0;
    re_chi(i) = (2/pi) * trapz(omega, integrand);
end
if median(re_chi(1:min(10,end))) < 0, re_chi = -re_chi; end

chi    = re_chi + 1i*im_chi;
Gfluid = ((1 ./ chi) - kappa) ./ (6 * builtin('pi') * a_um);
end


%% ===================== Tassieri =====================

function [omega, Gfluid] = tassieri_moduli_from_trace(x, t, fs, nfft, freq_limit, a_um, kappa, ...
    beta_oversample, taper_frac, qlog_base, max_tau_seconds)
x = x(:) - mean(x,'omitnan');
x = detrend(x,'linear');
[~, f_raw] = pwelch(x, hanning(nfft), nfft/2, nfft, fs);
f  = f_raw(2:end);
f  = f(f <= freq_limit);
omega = 2*builtin('pi')*f(:);

[tau_s, A_tau] = compute_npaf_quasilog(x, t(2)-t(1), qlog_base, max_tau_seconds);
if tau_s(1) == 0, A_tau(1) = 1; end
[t_os, A_os] = oversample_and_taper(tau_s, A_tau, t(2)-t(1), beta_oversample, taper_frac);
Ahat = evans_ft_eq9(t_os, A_os, omega(:), 1, 0);
Gbar_tot = 1 ./ ((1./(1i*omega(:).*Ahat)) - 1);
Gtot     = (kappa ./ (6*builtin('pi')*a_um)) .* Gbar_tot;
Gfluid   = Gtot - (kappa/(6*builtin('pi')*a_um));
end


%% ===================== Mason =====================

function [omega, Gfluid] = mason_moduli_from_trace(x, t, fs, nfft, freq_limit, kT_um, a_um, ...
    win, alpha_clamp, use_3D)
dt = median(diff(t));
x  = x(:) - mean(x,'omitnan');
x  = detrend(x,'linear');
[~, f_raw] = pwelch(x, hanning(nfft), nfft/2, nfft, fs);
f  = f_raw(2:end);
f  = f(f <= freq_limit);
omega = 2*builtin('pi')*f(:);

[tau_s, msd_1D] = compute_msd_quasilog(x, dt, 1.45, inf);
good = isfinite(msd_1D) & msd_1D > 0 & tau_s > 0;
tau  = tau_s(good);
MSD  = msd_1D(good);
if use_3D, MSD = 3*MSD; end

logt  = log(tau);
logm  = log(MSD);
alpha = local_log_slope(logt, logm, win);
alpha = neighbor_average(alpha, 1);

t_eval     = 1 ./ omega(:);
MSD_eval   = exp(interp1(logt, logm, log(t_eval), 'linear','extrap'));
alpha_eval = interp1(logt, alpha, log(t_eval), 'linear','extrap');
alpha_eval = max(alpha_clamp(1), min(alpha_clamp(2), alpha_eval));

Gmag   = kT_um ./ (builtin('pi') * a_um .* MSD_eval .* gamma(1 + alpha_eval));
Gfluid = Gmag .* cos(builtin('pi')*alpha_eval/2) + 1i * Gmag .* sin(builtin('pi')*alpha_eval/2);
end


%% ===================== HELPERS =====================

function [Xmat, t_use] = load_and_crop_stack(file_list, px_to_um, frame_time, use_full_length, bead_col)
if nargin < 5 || isempty(bead_col), bead_col = 1; end

Xmat  = [];
t_use = [];

for j = 1:numel(file_list)
    dat    = readmatrix(file_list{j});
    x_full = dat(:, bead_col) * px_to_um;
    N      = numel(x_full);

    if use_full_length
        use_idx = 1:N;
    else
        if N >= 9000
            use_idx = 3000 : min(12000, N);
        elseif N > 3000
            use_idx = 3000 : N;
        else
            warning('File %s has only %d points; using all.', file_list{j}, N);
            use_idx = 1:N;
        end
    end

    x = x_full(use_idx);
    t = (0:numel(x)-1).' * frame_time;

    if isempty(t_use)
        t_use = t;
        Xmat  = x;
    else
        L     = min(numel(t_use), numel(x));
        t_use = t_use(1:L);
        Xmat  = [Xmat(1:L,:), x(1:L)]; %#ok<AGROW>
    end
end
end


function dx = subtract_mean_motion(x, t, method, moving_window_sec)
x = x(:); t = t(:);
switch lower(method)
    case 'none'
        dx = x;
    case 'linear'
        p  = polyfit(t, x, 1);
        dx = x - polyval(p, t);
    case 'poly2'
        p  = polyfit(t, x, 2);
        dx = x - polyval(p, t);
    case 'moving'
        dt = median(diff(t));
        wN = max(5, round(moving_window_sec / max(dt,eps)));
        dx = x - movmean(x, wN, 'omitnan');
    otherwise
        error('Unknown mean_method "%s".', method);
end
end


function y_med = signed_log_median(Y)
sgn   = sign(median(Y, 2, 'omitnan'));
sgn(sgn==0) = 1;
y_med = sgn .* exp(median(log(abs(Y)+eps), 2, 'omitnan'));
end

function y = interp_signed_log(w_in, y_in, w_out)
w_in = w_in(:); y_in = y_in(:); w_out = w_out(:);
sgn  = sign(median(y_in,'omitnan'));
if sgn == 0, sgn = 1; end
logy = interp1(log(w_in), log(abs(y_in)+eps), log(w_out), 'linear','extrap');
y    = sgn .* exp(logy);
end

function Yout = interp_cols_signed_log(w_in, Yin, w_out)
w_in  = w_in(:);
w_out = w_out(:);
nCols = size(Yin,2);
Yout  = nan(numel(w_out), nCols);
for j = 1:nCols
    Yout(:,j) = interp_signed_log(w_in, Yin(:,j), w_out);
end
end

function [t_os, g_os] = oversample_and_taper(t, g, frame_time, beta_oversample, taper_frac)
t  = t(:); g = g(:);
dt_os = frame_time / beta_oversample;
t_os  = (0:dt_os:t(end)).';
g_os  = pchip(t, g, t_os);
Ntaper = max(10, round(taper_frac * numel(t_os)));
w = ones(size(g_os));
k0 = numel(g_os) - Ntaper + 1;
s  = linspace(0,1,Ntaper).';
w(k0:end) = 0.5*(1 + cos(builtin('pi')*s));
g_os = g_os .* w;
end

function ghat = evans_ft_eq9(t, g, omega, g0, gdot_inf)
t = t(:); g = g(:); omega = omega(:);
if t(1) ~= 0, t = t - t(1); end
N    = numel(t);
ghat = zeros(numel(omega),1);
if N < 3, return; end
dt    = diff(t);
dg    = diff(g);
slope = dg ./ dt;
t1 = t(2); g1 = g(2);
for m = 1:numel(omega)
    w = omega(m);
    if w == 0, ghat(m) = 0; continue; end
    E       = exp(-1i*w*t);
    term0   = 1i*w*g0;
    term1   = (1 - E(2)) * ((g1 - g0) / max(t1,eps));
    term_inf = gdot_inf * E(end);
    sumterm = sum(slope .* (E(1:end-1) - E(2:end)));
    ghat(m) = -(term0 + term1 + term_inf + sumterm) / (w^2);
end
end

function [tau_s, A_tau] = compute_npaf_quasilog(x, dt, base, max_tau_seconds)
x  = x(:); N = numel(x);
x2 = mean(x.^2,'omitnan');
if ~isfinite(x2) || x2 <= 0
    tau_s = 0; A_tau = 1; return;
end
nfft = 2^nextpow2(2*N);
X    = fft(x, nfft);
acf  = ifft(X .* conj(X), 'symmetric');
acf  = acf(1:N);
lags = (0:N-1).';
A_full = (acf ./ max(1, N - lags)) / x2;

lag_idx = [];
n = 0;
while true
    li = ceil(base^n);
    if li >= N, break; end
    lag_idx(end+1,1) = li; %#ok<AGROW>
    n = n+1;
end
lag_idx = unique([0;1;2;3;4;lag_idx]);
tau_s   = lag_idx * dt;
if isfinite(max_tau_seconds)
    keep    = tau_s <= max_tau_seconds;
    tau_s   = tau_s(keep);
    lag_idx = lag_idx(keep);
end
A_tau    = A_full(lag_idx+1);
A_tau(1) = 1;
end

function [tau_s, MSD_tau] = compute_msd_quasilog(x, dt, base, max_tau_seconds)
x  = x(:); N = numel(x);
nfft = 2^nextpow2(2*N);
X    = fft(x, nfft);
acf  = ifft(X .* conj(X), 'symmetric');
acf  = acf(1:N);
lags = (0:N-1).';
C    = acf ./ max(1, N - lags);
x2   = mean(x.^2,'omitnan');
MSD_full    = 2*(x2 - C);
MSD_full(1) = 0;

lag_idx = [];
n = 0;
while true
    li = ceil(base^n);
    if li >= N, break; end
    lag_idx(end+1,1) = li; %#ok<AGROW>
    n = n+1;
end
lag_idx = unique([0;1;2;3;4;lag_idx]);
tau_s   = lag_idx * dt;
if isfinite(max_tau_seconds)
    keep    = tau_s <= max_tau_seconds;
    tau_s   = tau_s(keep);
    lag_idx = lag_idx(keep);
end
MSD_tau = MSD_full(lag_idx+1);
end

function alpha = local_log_slope(logt, logm, win)
n = numel(logt);
if mod(win,2)==0 || win < 3, error('win must be odd >= 3'); end
h     = floor(win/2);
alpha = nan(n,1);
for i = 1:n
    i1 = max(1, i-h);
    i2 = min(n, i+h);
    xv = logt(i1:i2);
    yv = logm(i1:i2);
    x0 = mean(xv);
    d  = sum((xv-x0).^2);
    if d < eps
        alpha(i) = 0;
    else
        alpha(i) = sum((xv-x0).*(yv-mean(yv))) / d;
    end
end
end

function y = neighbor_average(x, nNbr)
x = x(:);
n = numel(x);
y = nan(n,1);
for i = 1:n
    y(i) = mean(x(max(1,i-nNbr):min(n,i+nNbr)), 'omitnan');
end
end

function [kappa, msd_plateau_mean] = calibrate_kappa_from_passive_files( ...
            file_list, px_to_um, bead_col, ...
            msd_plateau_frac, msd_min_points, kT_um, use_axis_mean_for_kappa)
% bead_col = 1 for left bead, 3 for right bead
% Uses both x and y columns for that bead, computes MSD, estimates plateau
% from final portion of MSD curve, then kappa = 2*kT / MSD_plateau.

    x_col = bead_col;
    y_col = bead_col + 1;

    kappa_vals = [];
    msd_plateaus = [];

    for j = 1:numel(file_list)
        dat = readmatrix(file_list{j});
        if size(dat,2) < y_col
            warning('Skipping %s: insufficient columns.', file_list{j});
            continue;
        end

        x = dat(:,x_col) * px_to_um;
        y = dat(:,y_col) * px_to_um;

        x = x - mean(x, 'omitnan');
        y = y - mean(y, 'omitnan');

        Lx = max(1, numel(x)-1);
        Ly = max(1, numel(y)-1);

        if Lx < msd_min_points || Ly < msd_min_points
            warning('Skipping %s: too short for plateau estimate.', file_list{j});
            continue;
        end

        msd_x = msd1d_full(x, Lx);
        msd_y = msd1d_full(y, Ly);

        px_plateau = estimate_msd_plateau(msd_x, msd_plateau_frac, msd_min_points);
        py_plateau = estimate_msd_plateau(msd_y, msd_plateau_frac, msd_min_points);

        if use_axis_mean_for_kappa
            p_mean = mean([px_plateau, py_plateau], 'omitnan');
            if isfinite(p_mean) && p_mean > 0
                msd_plateaus(end+1,1) = p_mean; %#ok<AGROW>
                kappa_vals(end+1,1) = 2 * kT_um / p_mean; %#ok<AGROW>
            end
        else
            vals = [px_plateau, py_plateau];
            vals = vals(isfinite(vals) & vals > 0);
            for q = 1:numel(vals)
                msd_plateaus(end+1,1) = vals(q); %#ok<AGROW>
                kappa_vals(end+1,1) = 2 * kT_um / vals(q); %#ok<AGROW>
            end
        end
    end

    if isempty(kappa_vals)
        warning('No valid passive calibration values found.');
        kappa = NaN;
        msd_plateau_mean = NaN;
        return;
    end

    kappa = median(kappa_vals, 'omitnan');
    msd_plateau_mean = median(msd_plateaus, 'omitnan');
end

function plateau = estimate_msd_plateau(msd, frac_tail, min_points)
% Estimate plateau as median of final fraction of MSD curve.

    msd = msd(:);
    msd = msd(isfinite(msd) & msd >= 0);

    if isempty(msd)
        plateau = NaN;
        return;
    end

    N = numel(msd);
    nTail = max(min_points, ceil(frac_tail * N));
    nTail = min(nTail, N);

    tail = msd(end-nTail+1:end);
    plateau = median(tail, 'omitnan');
end

function MSD = msd1d_full(traj, L)
% Standard 1D MSD including lag 0.
    traj = traj(:);
    N = numel(traj);
    L = min(L, N-1);

    MSD = zeros(L+1,1);
    MSD(1) = 0;

    for lag = 1:L
        MSD(lag+1) = mean((traj(1:end-lag) - traj(1+lag:end)).^2, 'omitnan');
    end
end