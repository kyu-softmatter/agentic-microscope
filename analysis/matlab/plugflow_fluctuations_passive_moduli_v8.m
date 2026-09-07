function plugflow_fluctuations_passive_moduli_v8
% V8 — full script with publication-quality master plot
% (colorblind-safe, open symbols, serif font, 1-100 rad/s, speeds 1/3/6)

clear; clc; close all;

%% ================= USER SETTINGS =================
px_to_um   = 0.065;
frame_time = 0.020407;
fs         = 1/frame_time;

a_um       = 2.5;
nfft       = 1024;
freq_limit = 20;      % Hz  (internal pipeline; plot is clipped to 1-100 rad/s)

kT_um = 4.045e-3;     % pN*um

x_col = 1;
y_col = 2;

fluct_method = 'kk';

kk_smooth_span_hz = 0.1;
kk_psd_halve      = true;
kk_pool_method    = 'median';

plot_kk_psd_debug = true;
exposure_time_s   = 0.020407;
exposure_floor    = 0.4;

beta_oversample = 1000;
taper_frac      = 0.25;
qlog_base       = 1.45;
max_tau_seconds = inf;

mason_win         = 7;
mason_alpha_clamp = [0, 1];
mason_use_3D      = false;

kappa_fit_mean_method = 'linear';
moving_window_sec = 2.0;

use_full_length_for_plug = false;

plot_each_file    = false;
plot_speed_median = true;
plot_power_median = true;

overlay_passive_if_present = true;

make_master_speed_plot = true;
master_speeds_to_show  = [1, 3, 6];   % um/s  ← only these three
master_speed_tol       = 1e-3;

f_master     = linspace(0.05, freq_limit, 250).';
omega_master = 2*pi*f_master;

use_bulk_rheology   = false;
plot_bulk_rheology  = false;
bulk_file           = '20260131_80%bf_WATER_GLYC_FreqSweep_5%_2.csv';
bulk_omega_min_plot = 5;

%% ======== LOAD BULK SAOS (optional) ========
if use_bulk_rheology
    bulk = readmatrix(bulk_file);
    Gp_bulk    = bulk(:,1);
    Gpp_bulk   = bulk(:,2);
    omega_bulk = bulk(:,4);

    ok = isfinite(Gp_bulk) & isfinite(Gpp_bulk) & isfinite(omega_bulk) & omega_bulk>0;
    Gp_bulk    = Gp_bulk(ok);
    Gpp_bulk   = Gpp_bulk(ok);
    omega_bulk = omega_bulk(ok);

    bulk_mask       = omega_bulk >= bulk_omega_min_plot;
    omega_bulk_plot = omega_bulk(bulk_mask);
    Gp_bulk_plot    = Gp_bulk(bulk_mask);
    Gpp_bulk_plot   = Gpp_bulk(bulk_mask);
else
    omega_bulk_plot = [];
    Gp_bulk_plot    = [];
    Gpp_bulk_plot   = [];
end

%% ================= LOAD FILES =================
files = dir('*.txt');
if isempty(files), error('No .txt files found.'); end
names = {files.name}; names = names(:);

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
    k = k+1;
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
    k = k+1;
    passMeta(k).name  = fn;
    passMeta(k).power = str2double(tokP{1}) * str2double(tokP{2});
    passMeta(k).ok    = true;
end

if isempty(plugMeta)
    error('No plug (creepx_) files found with expected naming patterns.');
end

uniqP = unique(vertcat(plugMeta.power));
fprintf('Plug powers detected: %s\n', mat2str(uniqP.',4));
fprintf('Method: %s | KKpool=%s\n', fluct_method, kk_pool_method);

%% ================= MASTER ACCUMULATORS =================
masterX = struct(); masterY = struct();
masterX.omega = omega_master(:); masterY.omega = omega_master(:);
masterX.V_list = []; masterY.V_list = [];
masterX.Gp_cols = {}; masterX.Gpp_cols = {};
masterY.Gp_cols = {}; masterY.Gpp_cols = {};
masterX.Gp_pass_cols = []; masterX.Gpp_pass_cols = [];
masterY.Gp_pass_cols = []; masterY.Gpp_pass_cols = [];

%% ================= LOOP OVER POWER =================
for ipow = 1:numel(uniqP)
    P = uniqP(ipow);

    %% -------- PASSIVE overlays --------
    have_passive = false;
    omega_pass_x = []; Gpass_x = [];
    omega_pass_y = []; Gpass_y = [];

    if overlay_passive_if_present && ~isempty(passMeta)
        idxs = find(abs(vertcat(passMeta.power) - P) < 1e-12);
        if ~isempty(idxs)
            have_passive = true;
            filesP = {passMeta(idxs).name};

            [omega_pass_x, Gpass_x] = extract_passive_component( ...
                filesP, x_col, true, ...
                px_to_um, frame_time, fs, nfft, freq_limit, ...
                kT_um, a_um, fluct_method, kk_smooth_span_hz, kk_psd_halve, kk_pool_method, ...
                beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
                mason_win, mason_alpha_clamp, mason_use_3D, ...
                plot_kk_psd_debug, exposure_time_s, exposure_floor, ...
                sprintf('PASSIVE-X P=%.4g',P));

            [omega_pass_y, Gpass_y] = extract_passive_component( ...
                filesP, y_col, true, ...
                px_to_um, frame_time, fs, nfft, freq_limit, ...
                kT_um, a_um, fluct_method, kk_smooth_span_hz, kk_psd_halve, kk_pool_method, ...
                beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
                mason_win, mason_alpha_clamp, mason_use_3D, ...
                plot_kk_psd_debug, exposure_time_s, exposure_floor, ...
                sprintf('PASSIVE-Y P=%.4g',P));

            if make_master_speed_plot
                masterX.Gp_pass_cols(:,end+1)  = interp_signed_log(omega_pass_x, real(Gpass_x),  masterX.omega);
                masterX.Gpp_pass_cols(:,end+1) = interp_signed_log(omega_pass_x, imag(Gpass_x),  masterX.omega);
                masterY.Gp_pass_cols(:,end+1)  = interp_signed_log(omega_pass_y, real(Gpass_y),  masterY.omega);
                masterY.Gpp_pass_cols(:,end+1) = interp_signed_log(omega_pass_y, imag(Gpass_y),  masterY.omega);
            end
        end
    end

    %% -------- Plug by speed --------
    pplug = vertcat(plugMeta.power);
    vplug = vertcat(plugMeta.speed);
    idxP  = find(abs(pplug - P) < 1e-12);
    speeds = unique(vplug(idxP));

    speedX = struct('speed',{},'omega',{},'Gp_med',{},'Gpp_med',{},'Gp_files',{},'Gpp_files',{});
    speedY = struct('speed',{},'omega',{},'Gp_med',{},'Gpp_med',{},'Gp_files',{},'Gpp_files',{});

    for si = 1:numel(speeds)
        V      = speeds(si);
        idxPV  = idxP(abs(vplug(idxP) - V) < 1e-12);
        filesPV = {plugMeta(idxPV).name};

        [omegaX, Gp_files_X, Gpp_files_X] = extract_plug_component( ...
            filesPV, x_col, ...
            px_to_um, frame_time, fs, nfft, freq_limit, ...
            kT_um, a_um, fluct_method, kk_smooth_span_hz, kk_psd_halve, ...
            beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
            mason_win, mason_alpha_clamp, mason_use_3D, ...
            use_full_length_for_plug, kappa_fit_mean_method, moving_window_sec, ...
            plot_kk_psd_debug, exposure_time_s, exposure_floor, ...
            sprintf('PLUG-X P=%.4g V=%.3g',P,V));

        speedX(end+1).speed    = V; %#ok<AGROW>
        speedX(end).omega      = omegaX;
        speedX(end).Gp_files   = Gp_files_X;
        speedX(end).Gpp_files  = Gpp_files_X;
        speedX(end).Gp_med     = signed_log_median(Gp_files_X);
        speedX(end).Gpp_med    = signed_log_median(Gpp_files_X);

        [omegaY, Gp_files_Y, Gpp_files_Y] = extract_plug_component( ...
            filesPV, y_col, ...
            px_to_um, frame_time, fs, nfft, freq_limit, ...
            kT_um, a_um, fluct_method, kk_smooth_span_hz, kk_psd_halve, ...
            beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
            mason_win, mason_alpha_clamp, mason_use_3D, ...
            use_full_length_for_plug, kappa_fit_mean_method, moving_window_sec, ...
            plot_kk_psd_debug, exposure_time_s, exposure_floor, ...
            sprintf('PLUG-Y P=%.4g V=%.3g',P,V));

        speedY(end+1).speed    = V; %#ok<AGROW>
        speedY(end).omega      = omegaY;
        speedY(end).Gp_files   = Gp_files_Y;
        speedY(end).Gpp_files  = Gpp_files_Y;
        speedY(end).Gp_med     = signed_log_median(Gp_files_Y);
        speedY(end).Gpp_med    = signed_log_median(Gpp_files_Y);

        if make_master_speed_plot
            if isempty(master_speeds_to_show) || any(abs(master_speeds_to_show - V) < master_speed_tol)

                Gp_interp_X  = interp_cols_signed_log(omegaX, Gp_files_X,  masterX.omega);
                Gpp_interp_X = interp_cols_signed_log(omegaX, Gpp_files_X, masterX.omega);
                idxVX = find(abs(masterX.V_list - V) < master_speed_tol, 1);
                if isempty(idxVX)
                    masterX.V_list(end+1,1) = V; %#ok<AGROW>
                    masterX.Gp_cols{end+1}  = Gp_interp_X;  %#ok<AGROW>
                    masterX.Gpp_cols{end+1} = Gpp_interp_X; %#ok<AGROW>
                else
                    masterX.Gp_cols{idxVX}  = [masterX.Gp_cols{idxVX},  Gp_interp_X];
                    masterX.Gpp_cols{idxVX} = [masterX.Gpp_cols{idxVX}, Gpp_interp_X];
                end

                Gp_interp_Y  = interp_cols_signed_log(omegaY, Gp_files_Y,  masterY.omega);
                Gpp_interp_Y = interp_cols_signed_log(omegaY, Gpp_files_Y, masterY.omega);
                idxVY = find(abs(masterY.V_list - V) < master_speed_tol, 1);
                if isempty(idxVY)
                    masterY.V_list(end+1,1) = V; %#ok<AGROW>
                    masterY.Gp_cols{end+1}  = Gp_interp_Y;  %#ok<AGROW>
                    masterY.Gpp_cols{end+1} = Gpp_interp_Y; %#ok<AGROW>
                else
                    masterY.Gp_cols{idxVY}  = [masterY.Gp_cols{idxVY},  Gp_interp_Y];
                    masterY.Gpp_cols{idxVY} = [masterY.Gpp_cols{idxVY}, Gpp_interp_Y];
                end
            end
        end
    end

    %% -------- Per-power median plots (X) --------
    [w_common_X, Gp_medP_X, Gpp_medP_X] = power_median_over_speeds(speedX, plot_power_median);

    figure; clf; hold on;
    if have_passive
        loglog(omega_pass_x, abs(real(Gpass_x)),  'k-',  'LineWidth',2.8, 'DisplayName',sprintf('Passive-x G'' @P=%.3g',P));
        loglog(omega_pass_x, abs(imag(Gpass_x)),  'k--', 'LineWidth',2.8, 'DisplayName',sprintf('Passive-x G'''' @P=%.3g',P));
    end
    for si = 1:numel(speedX)
        w = speedX(si).omega;
        if plot_each_file
            for jj = 1:size(speedX(si).Gp_files,2)
                loglog(w, abs(speedX(si).Gp_files(:,jj)),  '-',  'LineWidth',0.75,'HandleVisibility','off');
                loglog(w, abs(speedX(si).Gpp_files(:,jj)), '--', 'LineWidth',0.75,'HandleVisibility','off');
            end
        end
        if plot_speed_median
            loglog(w, abs(speedX(si).Gp_med),  '-',  'LineWidth',1.8,'DisplayName',sprintf('dx(x) V=%.3g  G''',  speedX(si).speed));
            loglog(w, abs(speedX(si).Gpp_med), '--', 'LineWidth',1.8,'DisplayName',sprintf('dx(x) V=%.3g  G''''',speedX(si).speed));
        end
    end
    if plot_power_median && ~isempty(Gp_medP_X)
        loglog(w_common_X, Gp_medP_X,  'r-',  'LineWidth',2.5,'DisplayName','dx(x) median speeds G''');
        loglog(w_common_X, Gpp_medP_X, 'r--', 'LineWidth',2.5,'DisplayName','dx(x) median speeds G''''');
    end
    grid on;
    xlabel('\omega (rad/s)'); ylabel('G'', G'''' (Pa)');
    title(sprintf('V8 X: P=%.3g | %s', P, upper(fluct_method)));
    set(gca,'XScale','log','YScale','log');
    legend('Location','best');

    %% -------- Per-power median plots (Y) --------
    [w_common_Y, Gp_medP_Y, Gpp_medP_Y] = power_median_over_speeds(speedY, plot_power_median);

    figure; clf; hold on;
    if have_passive
        loglog(omega_pass_y, abs(real(Gpass_y)),  'k-',  'LineWidth',2.8,'DisplayName',sprintf('Passive-y G'' @P=%.3g',P));
        loglog(omega_pass_y, abs(imag(Gpass_y)),  'k--', 'LineWidth',2.8,'DisplayName',sprintf('Passive-y G'''' @P=%.3g',P));
    end
    for si = 1:numel(speedY)
        w = speedY(si).omega;
        if plot_each_file
            for jj = 1:size(speedY(si).Gp_files,2)
                loglog(w, abs(speedY(si).Gp_files(:,jj)),  '-',  'LineWidth',0.75,'HandleVisibility','off');
                loglog(w, abs(speedY(si).Gpp_files(:,jj)), '--', 'LineWidth',0.75,'HandleVisibility','off');
            end
        end
        if plot_speed_median
            loglog(w, abs(speedY(si).Gp_med),  '-',  'LineWidth',1.8,'DisplayName',sprintf('dy(y) V=%.3g  G''',  speedY(si).speed));
            loglog(w, abs(speedY(si).Gpp_med), '--', 'LineWidth',1.8,'DisplayName',sprintf('dy(y) V=%.3g  G''''',speedY(si).speed));
        end
    end
    if plot_power_median && ~isempty(Gp_medP_Y)
        loglog(w_common_Y, Gp_medP_Y,  'r-',  'LineWidth',2.5,'DisplayName','dy(y) median speeds G''');
        loglog(w_common_Y, Gpp_medP_Y, 'r--', 'LineWidth',2.5,'DisplayName','dy(y) median speeds G''''');
    end
    grid on;
    xlabel('\omega (rad/s)'); ylabel('G'', G'''' (Pa)');
    title(sprintf('V8 Y: P=%.3g | %s', P, upper(fluct_method)));
    set(gca,'XScale','log','YScale','log','FontSize',14);
    legend('Location','best');

end % power loop


%% ================= MASTER PLOTS =================
if make_master_speed_plot
    do_bulk = use_bulk_rheology && plot_bulk_rheology;
    plot_master(masterX, 'V8 master (X): dx, \kappa from x', do_bulk, omega_bulk_plot, Gp_bulk_plot, Gpp_bulk_plot);
    plot_master(masterY, 'V8 master (Y): dy, \kappa from y', do_bulk, omega_bulk_plot, Gp_bulk_plot, Gpp_bulk_plot);
end

end % main


%% ===================== PASSIVE extraction =====================
function [omega, Gpass] = extract_passive_component( ...
    file_list, comp_col, use_full_length, ...
    px_to_um, frame_time, fs, nfft, freq_limit, ...
    kT_um, a_um, method, kk_smooth_span_hz, kk_psd_halve, kk_pool_method, ...
    beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
    mason_win, mason_alpha_clamp, mason_use_3D, ...
    plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag) %#ok<INUSL>

[Xmat, t_use] = load_and_crop_stack_onecol(file_list, comp_col, px_to_um, frame_time, use_full_length);
nFiles = size(Xmat,2);

omega = [];
Gcols = [];

for j = 1:nFiles
    x = Xmat(:,j);
    kappa = estimate_kappa_from_component(x, t_use, kT_um, 'none', 0);

    [omega_j, G_j] = extract_moduli_from_trace_component( ...
        x, t_use, fs, nfft, freq_limit, kT_um, a_um, kappa, ...
        method, kk_smooth_span_hz, kk_psd_halve, ...
        beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
        mason_win, mason_alpha_clamp, mason_use_3D, ...
        plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag, j);

    if isempty(omega)
        omega = omega_j(:);
        Gcols = nan(numel(omega), nFiles);
    end
    Gcols(:,j) = interp1(omega_j, G_j, omega, 'linear', 'extrap');
end

Gp_med  = signed_log_median(real(Gcols));
Gpp_med = signed_log_median(imag(Gcols));
Gpass   = Gp_med + 1i*Gpp_med;
end


%% ===================== PLUG extraction =====================
function [omega, Gp_files, Gpp_files] = extract_plug_component( ...
    file_list, comp_col, ...
    px_to_um, frame_time, fs, nfft, freq_limit, ...
    kT_um, a_um, method, kk_smooth_span_hz, kk_psd_halve, ...
    beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
    mason_win, mason_alpha_clamp, mason_use_3D, ...
    use_full_length, kappa_fit_mean_method, moving_window_sec, ...
    plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag)

[Xmat, t_use] = load_and_crop_stack_onecol(file_list, comp_col, px_to_um, frame_time, use_full_length);
nFiles = size(Xmat,2);

omega     = [];
Gp_files  = [];
Gpp_files = [];

for j = 1:nFiles
    x  = Xmat(:,j);
    dx = x - mean(x,'omitnan');
    kappa = estimate_kappa_from_component(x, t_use, kT_um, kappa_fit_mean_method, moving_window_sec);

    [omega_j, G_j] = extract_moduli_from_trace_component( ...
        dx, t_use, fs, nfft, freq_limit, kT_um, a_um, kappa, ...
        method, kk_smooth_span_hz, kk_psd_halve, ...
        beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
        mason_win, mason_alpha_clamp, mason_use_3D, ...
        plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag, j);

    if isempty(omega)
        omega     = omega_j(:);
        Gp_files  = nan(numel(omega), nFiles);
        Gpp_files = nan(numel(omega), nFiles);
    end
    Gp_files(:,j)  = interp1(omega_j, real(G_j), omega, 'linear', 'extrap');
    Gpp_files(:,j) = interp1(omega_j, imag(G_j), omega, 'linear', 'extrap');
end
end


%% ===================== per-power median over speeds =====================
function [w_common, Gp_medP, Gpp_medP] = power_median_over_speeds(speedStruct, do_it)
if ~do_it || numel(speedStruct) < 2
    w_common = []; Gp_medP = []; Gpp_medP = [];
    return;
end

w_common = speedStruct(1).omega(:);
Gp_mat   = nan(numel(w_common), numel(speedStruct));
Gpp_mat  = nan(numel(w_common), numel(speedStruct));

for si = 1:numel(speedStruct)
    w   = speedStruct(si).omega(:);
    gp  = speedStruct(si).Gp_med(:);
    gpp = speedStruct(si).Gpp_med(:);
    Gp_mat(:,si)  = interp_signed_log(w, gp,  w_common);
    Gpp_mat(:,si) = interp_signed_log(w, gpp, w_common);
end

Gp_medP  = abs(signed_log_median(Gp_mat));
Gpp_medP = abs(signed_log_median(Gpp_mat));
end


%% ===================== MASTER plotting (publication quality) =====================
function plot_master(master, ttl, plot_bulk, omega_bulk_plot, Gp_bulk_plot, Gpp_bulk_plot)

fig = figure('Color','w','Units','centimeters','Position',[2 2 8 7]);
ax  = axes('Parent',fig);
hold(ax,'on');
box(ax,'off');   % removes top and right axis lines entirely

pub_font   = 'Helvetica';
pub_fs     = 14;
lw_data    = 1.5;
lw_passive = 2;
mk_sz      = 7;

set(ax, 'XScale','log','YScale','log', ...
        'FontSize',pub_fs,'FontName',pub_font, ...
        'TickDir','out','TickLength',[0.025 0.025], ...
        'LineWidth',1.2, ...                          % thicker axis lines + ticks
        'XMinorTick','on','YMinorTick','on', ...
        'XColor','k','YColor','k', ...
        'XLim',[1 100]);

% Draw only left and bottom axis lines (no top/right)
% Draw only left and bottom axis lines (no top/right)
ax.XAxis.LineWidth = 1.2;
ax.YAxis.LineWidth = 1.2;

xlabel(ax, '\omega  (rad s^{-1})', 'FontSize',pub_fs,'FontName',pub_font,'Interpreter','tex');
ylabel(ax, 'G'', G''''  (Pa)',     'FontSize',pub_fs,'FontName',pub_font,'Interpreter','tex');

% Colorblind-safe (Wong 2011): near-black, blue, vermillion, bluish-green
cb_colors = [
    0.10, 0.10, 0.10;
    0.00, 0.45, 0.70;
    0.84, 0.37, 0.00;
    0.00, 0.62, 0.45;
];

markers = {'o','d','^','s'};

h_gp     = gobjects(0);
h_gpp    = gobjects(0);
lbl_rows = {};

%% Wi=0 (passive)
have_passive = ~isempty(master.Gp_pass_cols);
if have_passive
    Gp_pass_med  = signed_log_median(master.Gp_pass_cols);
    Gpp_pass_med = signed_log_median(master.Gpp_pass_cols);
    c = cb_colors(1,:);

    h1 = loglog(ax, master.omega, abs(Gp_pass_med), '-', ...
        'Color',c,'LineWidth',lw_passive, ...
        'MarkerSize',mk_sz,'MarkerFaceColor','none','MarkerEdgeColor',c);
    h2 = loglog(ax, master.omega, abs(Gpp_pass_med), '--', ...
        'Color',c,'LineWidth',lw_passive, ...
        'MarkerSize',mk_sz,'MarkerFaceColor','none','MarkerEdgeColor',c);

    h_gp(end+1)  = h1;
    h_gpp(end+1) = h2;
    lbl_rows{end+1} = 'Wi = 0';
end

%% Flow Wi rows
V_used = master.V_list(:);
if ~isempty(V_used)
    [V_sorted, sort_order] = sort(V_used);
    Wi_sorted = 1.1 .* V_sorted;
    Gp_cells  = master.Gp_cols(sort_order);
    Gpp_cells = master.Gpp_cols(sort_order);

    for i = 1:numel(Wi_sorted)
        ci  = min(i+1, size(cb_colors,1));
        c   = cb_colors(ci,:);

        Gp_med  = signed_log_median(Gp_cells{i});
        Gpp_med = signed_log_median(Gpp_cells{i});

        h1 = loglog(ax, master.omega, abs(Gp_med), '-', ...
            'Color',c,'LineWidth',lw_data, ...
            'MarkerSize',mk_sz,'MarkerFaceColor','none','MarkerEdgeColor',c);
        h2 = loglog(ax, master.omega, abs(Gpp_med), '--', ...
            'Color',c,'LineWidth',lw_data, ...
            'MarkerSize',mk_sz,'MarkerFaceColor','none','MarkerEdgeColor',c);

        h_gp(end+1)  = h1;
        h_gpp(end+1) = h2;
        lbl_rows{end+1} = sprintf('Wi = %.3g', Wi_sorted(i));
    end
end

%% Bulk SAOS
if plot_bulk && ~isempty(omega_bulk_plot)
    hb1 = loglog(ax, omega_bulk_plot, Gp_bulk_plot, '+', ...
        'Color','k','MarkerSize',mk_sz,'LineWidth',0.8);
    hb2 = loglog(ax, omega_bulk_plot, Gpp_bulk_plot, 'x', ...
        'Color','k','MarkerSize',mk_sz,'LineWidth',0.8);
    h_gp(end+1)  = hb1;
    h_gpp(end+1) = hb2;
    lbl_rows{end+1} = 'SAOS';
end

%% 2-column legend
nRows = numel(h_gp);
h_interleaved   = gobjects(1, 2*nRows);
lbl_interleaved = cell(1, 2*nRows);

for r = 1:nRows
    h_interleaved(2*r-1) = h_gp(r);
    h_interleaved(2*r)   = h_gpp(r);
    lbl_interleaved{2*r-1} = lbl_rows{r};
    lbl_interleaved{2*r}   = lbl_rows{r};
end

hdr_gp  = plot(ax, NaN, NaN, 'w', 'LineWidth', 0.01);
hdr_gpp = plot(ax, NaN, NaN, 'w', 'LineWidth', 0.01);

h_all   = [hdr_gp,            hdr_gpp,              h_interleaved];
lbl_all = [{'{\bfG''}'}, {'{\bfG''''}'}, lbl_interleaved];

legend(ax, h_all, lbl_all, ...
    'NumColumns',  2, ...
    'Location',    'northwest', ...
    'FontSize',    pub_fs - 1, ...
    'FontName',    pub_font, ...
    'Box',         'on', ...
    'EdgeColor',   'k', ...
    'LineWidth',   0.5, ...
    'Interpreter', 'tex');

ax.XTick = [1 10 100];
ax.XTickLabel = {'1','10','100'};
grid(ax,'off');
title(ax, ttl, 'FontSize',pub_fs-1,'FontName',pub_font,'FontWeight','normal','Interpreter','tex');
set(fig,'PaperPositionMode','auto');
end

%% ===================== CORE extraction dispatch =====================
function [omega, Gfluid] = extract_moduli_from_trace_component( ...
    x, t, fs, nfft, freq_limit, kT_um, a_um, kappa, ...
    method, kk_smooth_span_hz, kk_psd_halve, ...
    beta_oversample, taper_frac, qlog_base, max_tau_seconds, ...
    mason_win, mason_alpha_clamp, mason_use_3D, ...
    plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag, trace_idx)

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


%% ===================== Trap stiffness =====================
function kappa = estimate_kappa_from_component(x, t, kT_um, mean_method, moving_window_sec)
x = x(:); t = t(:);
if nargin < 4 || isempty(mean_method), mean_method = 'linear'; end

switch lower(mean_method)
    case 'none'
        xf = x;
    case 'linear'
        p  = polyfit(t, x, 1);
        xf = x - polyval(p, t);
    case 'poly2'
        p  = polyfit(t, x, 2);
        xf = x - polyval(p, t);
    case 'moving'
        dt = median(diff(t));
        wN = max(5, round(moving_window_sec / max(dt, eps)));
        xb = movmean(x, wN, 'omitnan');
        xf = x - xb;
    otherwise
        error('Unknown mean_method "%s".', mean_method);
end

xf    = xf - mean(xf,'omitnan');
xf    = detrend(xf,'linear');
v     = var(xf, 0, 'omitnan');
kappa = kT_um / (v + eps);
end


%% ===================== KK =====================
function [omega, Gfluid] = kk_moduli_from_trace(x, fs, nfft, freq_limit, kT_um, a_um, kappa, ...
    smooth_span_hz, kk_psd_halve, plot_kk_psd_debug, exposure_time_s, exposure_floor, debug_tag, trace_idx)

x = x(:);
x = x - mean(x,'omitnan');
x = detrend(x,'linear');

[Pxx, f_raw] = pwelch(x, hanning(nfft), nfft/2, nfft, fs);
f   = f_raw(2:end);
Pxx = Pxx(2:end);

keep = f <= freq_limit;
f   = f(keep);
Pxx = Pxx(keep);

Te       = exposure_time_s;
H2       = (sin(pi*f*Te) ./ (pi*f*Te)).^2;
H2(f==0) = 1;
H2_clip  = max(H2, exposure_floor);
PSD_corr = Pxx ./ H2_clip;

PSD_use = PSD_corr;
if kk_psd_halve
    PSD_use = PSD_use ./ 2;
end

if smooth_span_hz > 0
    log_psd_smooth = smooth(log10(f), log10(PSD_use + eps), smooth_span_hz, 'rlowess');
    PSD_smooth = 10.^log_psd_smooth;
else
    PSD_smooth = PSD_use;
end

if plot_kk_psd_debug
    figure(7100 + trace_idx); clf;
    loglog(f, Pxx./2,       'k.', 'DisplayName','Raw PSD'); hold on;
    loglog(f, PSD_corr./2,  'r-', 'LineWidth',1.5,'DisplayName','Exposure-corrected');
    loglog(f, PSD_smooth,   'b-', 'LineWidth',2.0,'DisplayName','Smoothed (used)');
    grid on;
    xlabel('f (Hz)'); ylabel('PSD (\mum^2/Hz)');
    title(sprintf('KK PSD: %s trace %d', debug_tag, trace_idx));
    yyaxis right;
    semilogx(f, H2,      'g--','LineWidth',1.2,'DisplayName','|sinc|^2');
    semilogx(f, H2_clip, 'm-', 'LineWidth',1.2,'DisplayName','H2 clipped');
    ylabel('|H(f)|^2'); ylim([0 1.05]);
    legend('Location','southwest');
end

omega  = 2*pi*f(:);
im_chi = -(omega .* PSD_smooth) / (2 * kT_um);
re_chi = zeros(size(im_chi));

for i = 1:numel(omega)
    w0        = omega(i);
    numerator = (omega .* im_chi) - (w0 * im_chi(i));
    denom     = omega.^2 - w0^2;
    integrand = numerator ./ denom;
    integrand(i) = 0;
    re_chi(i) = (2/pi) * trapz(omega, integrand);
end

if median(re_chi(1:min(10,end))) < 0
    re_chi = -re_chi;
end

chi    = re_chi + 1i*im_chi;
Gfluid = ((1 ./ chi) - kappa) ./ (6 * pi * a_um);
end


%% ===================== Tassieri =====================
function [omega, Gfluid] = tassieri_moduli_from_trace(x, t, fs, nfft, freq_limit, a_um, kappa, ...
    beta_oversample, taper_frac, qlog_base, max_tau_seconds)

x = x(:);
x = x - mean(x,'omitnan');
x = detrend(x,'linear');

[~, f_raw] = pwelch(x, hanning(nfft), nfft/2, nfft, fs);
f    = f_raw(2:end);
keep = f <= freq_limit;
f    = f(keep);
omega = 2*pi*f(:);

[tau_s, A_tau] = compute_npaf_quasilog(x, t(2)-t(1), qlog_base, max_tau_seconds);
if tau_s(1)==0, A_tau(1)=1; end

[t_os, A_os] = oversample_and_taper(tau_s, A_tau, (t(2)-t(1)), beta_oversample, taper_frac);

Ahat     = evans_ft_eq9(t_os, A_os, omega(:), 1, 0);
Gbar_tot = 1 ./ ((1./(1i*omega(:).*Ahat)) - 1);
Gtot     = (kappa ./ (6*pi*a_um)) .* Gbar_tot;
Gfluid   = Gtot - (kappa/(6*pi*a_um));
end


%% ===================== Mason =====================
function [omega, Gfluid] = mason_moduli_from_trace(x, t, fs, nfft, freq_limit, kT_um, a_um, ...
    win, alpha_clamp, use_3D)

dt = median(diff(t));
x  = x(:);
x  = x - mean(x,'omitnan');
x  = detrend(x,'linear');

[~, f_raw] = pwelch(x, hanning(nfft), nfft/2, nfft, fs);
f    = f_raw(2:end);
keep = f <= freq_limit;
f    = f(keep);
omega = 2*pi*f(:);

[tau_s, msd_1D] = compute_msd_quasilog(x, dt, 1.45, inf);

good  = isfinite(msd_1D) & msd_1D > 0 & tau_s > 0;
tau   = tau_s(good);
MSD   = msd_1D(good);
if use_3D, MSD = 3*MSD; end

logt = log(tau);
logm = log(MSD);
alpha = local_log_slope(logt, logm, win);
alpha = neighbor_average(alpha, 1);

t_eval     = 1 ./ omega(:);
MSD_eval   = exp(interp1(logt, logm,  log(t_eval), 'linear', 'extrap'));
alpha_eval = interp1(logt, alpha, log(t_eval), 'linear', 'extrap');
alpha_eval = max(alpha_clamp(1), min(alpha_clamp(2), alpha_eval));

Gmag   = kT_um ./ (pi * a_um .* MSD_eval .* gamma(1 + alpha_eval));
Gp     = Gmag .* cos(pi * alpha_eval / 2);
Gpp    = Gmag .* sin(pi * alpha_eval / 2);
Gfluid = Gp + 1i*Gpp;
end


%% ===================== IO HELPERS =====================
function [Xmat, t_use] = load_and_crop_stack_onecol(file_list, col, px_to_um, frame_time, use_full_length)
Xmat  = [];
t_use = [];

for j = 1:numel(file_list)
    dat = load(file_list{j});
    if size(dat,2) < col
        error('File %s has only %d columns, requested col=%d.', file_list{j}, size(dat,2), col);
    end

    x_full = dat(:,col) * px_to_um;
    N      = numel(x_full);

    if use_full_length
        use_idx = 1:N;
    else
        if N <= 9000
            use_idx = 3000:N;
        else
            use_idx = 3000:min(12000, N);
        end
    end

    x = x_full(use_idx);
    t = (0:numel(x)-1).' * frame_time;

    if isempty(t_use)
        t_use = t;
    else
        L     = min(numel(t_use), numel(t));
        t_use = t_use(1:L);
        x     = x(1:L);
        Xmat  = Xmat(1:L,:);
    end
    Xmat(:,j) = x; %#ok<AGROW>
end
end


%% ===================== MEDIAN + INTERP =====================
function y_med = signed_log_median(Y)
sgn       = sign(median(Y, 2, 'omitnan'));
sgn(sgn==0) = 1;
y_med     = sgn .* exp(median(log(abs(Y)+eps), 2, 'omitnan'));
end

function y = interp_signed_log(w_in, y_in, w_out)
w_in  = w_in(:); y_in = y_in(:); w_out = w_out(:);
sgn   = sign(median(y_in,'omitnan')); if sgn==0, sgn=1; end
logy  = interp1(log(w_in), log(abs(y_in)+eps), log(w_out), 'linear', 'extrap');
y     = sgn .* exp(logy);
end

function Yout = interp_cols_signed_log(w_in, Yin, w_out)
w_in  = w_in(:); w_out = w_out(:);
nCols = size(Yin,2);
Yout  = nan(numel(w_out), nCols);
for j = 1:nCols
    Yout(:,j) = interp_signed_log(w_in, Yin(:,j), w_out);
end
end


%% ===================== Evans/Tassieri helpers =====================
function [t_os, g_os] = oversample_and_taper(t, g, frame_time, beta_oversample, taper_frac)
t     = t(:); g = g(:);
dt_os = frame_time / beta_oversample;
t_os  = (0:dt_os:t(end)).';
g_os  = pchip(t, g, t_os);

Ntaper = max(10, round(taper_frac * numel(t_os)));
w      = ones(size(g_os));
k0     = numel(g_os) - Ntaper + 1;
s      = linspace(0,1,Ntaper).';
w(k0:end) = 0.5*(1 + cos(pi*s));
g_os  = g_os .* w;
end

function ghat = evans_ft_eq9(t, g, omega, g0, gdot_inf)
t     = t(:); g = g(:); omega = omega(:);
if t(1) ~= 0, t = t - t(1); end
N     = numel(t);
ghat  = zeros(numel(omega),1);
if N < 3, return; end

dt    = diff(t);
dg    = diff(g);
slope = dg ./ dt;
t1    = t(2);
g1    = g(2);

for m = 1:numel(omega)
    w = omega(m);
    if w == 0, ghat(m) = 0; continue; end
    E        = exp(-1i*w*t);
    term0    = 1i*w*g0;
    term1    = (1 - E(2)) * ((g1 - g0) / max(t1, eps));
    term_inf = gdot_inf * E(end);
    sumterm  = sum(slope .* (E(1:end-1) - E(2:end)));
    rhs      = term0 + term1 + term_inf + sumterm;
    ghat(m)  = -(rhs) / (w^2);
end
end

function [tau_s, A_tau] = compute_npaf_quasilog(x, dt, base, max_tau_seconds)
x  = x(:);
N  = numel(x);
x2 = mean(x.^2,'omitnan');
if ~isfinite(x2) || x2<=0
    tau_s = 0; A_tau = 1; return;
end

nfft_ = 2^nextpow2(2*N);
X     = fft(x, nfft_);
acf   = ifft(X .* conj(X), 'symmetric');
acf   = acf(1:N);

lags     = (0:N-1).';
acf_unb  = acf ./ max(1, (N - lags));
A_full   = acf_unb / x2;

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


%% ===================== MSD helpers =====================
function [tau_s, MSD_tau] = compute_msd_quasilog(x, dt, base, max_tau_seconds)
x  = x(:);
N  = numel(x);

nfft_ = 2^nextpow2(2*N);
X     = fft(x, nfft_);
acf   = ifft(X .* conj(X), 'symmetric');
acf   = acf(1:N);

lags     = (0:N-1).';
C        = acf ./ max(1, (N - lags));
x2       = mean(x.^2,'omitnan');
MSD_full = 2*(x2 - C);
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
if mod(win,2)==0 || win<3
    error('win must be an odd integer >= 3');
end
h     = floor(win/2);
alpha = nan(n,1);
for i = 1:n
    i1 = max(1, i-h);
    i2 = min(n, i+h);
    xv = logt(i1:i2);
    yv = logm(i1:i2);
    x0 = mean(xv);
    dn = sum((xv-x0).^2);
    if dn < eps
        alpha(i) = 0;
    else
        alpha(i) = sum((xv-x0).*(yv-mean(yv))) / dn;
    end
end
end

function y = neighbor_average(x, nNbr)
x = x(:);
n = numel(x);
y = nan(n,1);
for i = 1:n
    i1   = max(1, i-nNbr);
    i2   = min(n, i+nNbr);
    y(i) = mean(x(i1:i2),'omitnan');
end
end
