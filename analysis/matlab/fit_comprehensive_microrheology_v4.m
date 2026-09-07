function fit_comprehensive_microrheology
% Comprehensive Microrheology: Spectral Averaging Version
% Methodologies: Individual PSD averaging + Direct Extraction
% Units: pN, um, s, Pa
clear; clc;

%% ================= USER SETTINGS =================
close_existing_figures = true;
use_tassieri_method    = false; % false: pwelch (Standard)
plot_real_data = true;
plot_oldroyd_fit = true;


frame_time = 0.02;              % s
fs = 1/frame_time;              % Hz
px_to_um   = 0.065;             % um/px
Nmodes_OB = 3;                  % number of polymer modes
nfft = 2048;
fit_freq_range = [0.1, 10];     % Range for Oldroyd-B fit
freq_limit = 10;                % Hz - Cutoff for all analysis

smooth_span = 0.2; %Hz

% --- THERMODYNAMICS & GEOMETRY ---
kT_um  = 4.045e-3;              % pN*um
a_um   = 2.5;                   % um
mu_PaS = 0.12;                  % Pa*s (nominal solvent)
gamma0_um = 6 * pi * mu_PaS * a_um;

% --- SAOS REFERENCE DATA ---
saos.lambdas = [2.05, 0.056, 0.0022];
saos.mus     = [0.042, 0.023, 0.07];
saos.mu_s    = 0.025;

if close_existing_figures, close all; end
files = dir('*.txt');
if isempty(files), error('No .txt files found'); end

%% ---------- Parse & Grouping ----------
filePowers = nan(numel(files),1);
for i = 1:numel(files)
    tok = regexp(files(i).name,'_(\d*\.?\d+)_OT(\d*\.?\d+)','tokens','once');
    if ~isempty(tok)
        filePowers(i) = str2double(tok{1}) * str2double(tok{2});
    end
end
uniqueP = unique(filePowers(~isnan(filePowers)));

%% ========== MAIN LOOP ==========
for gi = 1:numel(uniqueP)
    idxs = find(filePowers == uniqueP(gi));
    P = uniqueP(gi);
    
    psd_accumulator = []; 
    
    % --- 1) SPECTRAL AVERAGING ---
    for j = 1:numel(idxs)
        dat = load(files(idxs(j)).name);
        pos = dat(:,1) * px_to_um; % X-axis
        pos = pos - mean(pos, 'omitnan'); % Remove DC for this segment
        
        [psd_temp, f_raw] = pwelch(pos, hanning(nfft), nfft/2, nfft, fs);
        
        % Accumulate (skip DC)
        if j == 1
            f_exp = f_raw(2:end);
        end
        psd_accumulator(:,j) = psd_temp(2:end);
    end
    
    % Average spectra across files
    PSD_mean = mean(psd_accumulator, 2);
    
    % Apply Truncation
    valid_idx = f_exp <= freq_limit;
    f_exp    = f_exp(valid_idx);
    PSD_mean = PSD_mean(valid_idx);
    omega    = 2 * pi * f_exp;

    % --- 2) Nmodes_OB FIT TO SMOOTHED PSD ---
    % Pre-smooth for fitting stability
    log_psd_smooth = sgolayfilt(log10(PSD_mean), 2, 15); 
    PSD_smooth = 10.^log_psd_smooth;
    log_psd_smooth = smooth(log10(f_exp), log10(PSD_mean), 0.1, 'lowess');
    PSD_smooth = 10.^(log_psd_smooth);
    
    % Initial Guess for k from variance (equipartition)
    % (Approximated from the averaged PSD magnitude at low f)
    vars = zeros(numel(idxs),1);
    for j=1:numel(idxs)
        dat = load(files(idxs(j)).name);
        x = dat(:,1)*px_to_um;
        x = detrend(x,'linear');
        vars(j) = var(x,0,'omitnan');
    end
    var_init = mean(vars,'omitnan');
    k_init = kT_um/(var_init + eps);

    
    gs_seed   = gamma0_um;
    gp_seeds  = (gamma0_um / Nmodes_OB) * ones(1, Nmodes_OB);
    lam_seeds = logspace(-2, 0.5, Nmodes_OB);
    p0 = [gs_seed, gp_seeds, lam_seeds, k_init];
    
    lb = [gs_seed*0.1, zeros(1,Nmodes_OB), 1e-3*ones(1,Nmodes_OB), 0.5*k_init];
    ub = [gs_seed*5.0, 500*gamma0_um*ones(1,Nmodes_OB), 5.0*ones(1,Nmodes_OB), 2.0*k_init];
    
    resid = @(p) real(log10(ob_nmode_psd_model(f_exp, p, kT_um, Nmodes_OB) + eps) ...
                    - log10(PSD_smooth + eps));
    
    opts = optimoptions('lsqnonlin','Display','off','MaxIterations',800);
    pfit = lsqnonlin(resid, p0, lb, ub, opts);
    
    % Unpack
    gs_fit   = pfit(1);
    gp_fits  = pfit(2:1+Nmodes_OB);
    lam_fits = pfit(2+Nmodes_OB : 1+2*Nmodes_OB);
    k_fit    = pfit(end);

    %% ---------- PRINT FIT TABLE ----------
    drag_scale = 6*pi*a_um;
    mu_s_fit = gs_fit / drag_scale;
    mu_p_fit = gp_fits / drag_scale;
    G0_fit   = mu_p_fit ./ lam_fits;
    
    fprintf('\n=== OT Fit Summary: P = %.6g ===\n', P);
    fprintf('k_fit      = %.6g  (pN/um)\n', k_fit);
    fprintf('mu_s_fit   = %.6g  (Pa*s)\n', mu_s_fit);
    
    Row = {}; OT = []; SA = [];
    Row{end+1,1} = 'k_trap (pN/um)'; OT(end+1,1) = k_fit;     SA(end+1,1) = NaN;
    Row{end+1,1} = 'mu_s (Pa*s)';   OT(end+1,1) = mu_s_fit;  SA(end+1,1) = saos.mu_s;
    
    for m = 1:Nmodes_OB
        Row{end+1,1} = sprintf('Mode %d: lambda (s)', m);
        OT(end+1,1)  = lam_fits(m);
        SA(end+1,1)  = (m <= numel(saos.lambdas)) * saos.lambdas(min(m,numel(saos.lambdas))) + (m > numel(saos.lambdas))*NaN;
        
        Row{end+1,1} = sprintf('Mode %d: mu (Pa*s)', m);
        OT(end+1,1)  = mu_p_fit(m);
        SA(end+1,1)  = (m <= numel(saos.mus)) * saos.mus(min(m,numel(saos.mus))) + (m > numel(saos.mus))*NaN;
    end
    disp(table(SA, OT, 'RowNames', Row));

     %% --- 3) DIRECT RHEOLOGY EXTRACTION (GSER-ish) ---
    % 
    % log_f = log10(f_exp);
    % alpha = [diff(log_psd_smooth)./diff(log_f); 0];   % local log-slope
    log_psd_smooth = smooth(log10(f_exp), log10(PSD_mean), 0.1, 'lowess');
    PSD_smooth = 10.^(log_psd_smooth);
    omega = 2*pi*f_exp;
    % 
    % % From FDT: Sxx(omega) = (2kT/omega)*Im{chi(omega)}  ->  Im{chi} ~ omega*Sxx/(2kT)
    im_chi = -(omega .* PSD_smooth) / (2 * kT_um);


    %Approximate KK using local power-law slope
    % re_chi = im_chi .* tan(pi * alpha / 2);
    %--- Rigorous Kramers-Kronig Integral (No Power Law Assumption) ---
    re_chi = zeros(size(im_chi));
    for i = 1:length(omega)
        w0 = omega(i);
        % We compute the Principal Value integral by subtracting the singularity
        % Integral = Sum [ (xi*chi''(xi) - w0*chi''(w0)) / (xi^2 - w0^2) ] * dxi

        numerator = (omega .* im_chi) - (w0 * im_chi(i));
        denominator = (omega.^2 - w0^2);

        % Handle singularity at xi = w0 (use L'Hopital / derivative for the point itself)
        % Ideally we just skip the point i in the sum or rely on the subtraction to zero it
        integrand = numerator ./ denominator;
        integrand(i) = 0; % Remove the 0/0 singularity explicitly

        % Trapezoidal integration
        integral_val = trapz(omega, integrand);

        re_chi(i) = (2/pi) * integral_val;
        % Physical sign fix: static compliance should be positive
    end
    if median(re_chi(1:min(10,end))) < 0
            re_chi = -re_chi;
    end
    chi_direct = re_chi + 1i*im_chi;


    % Trapped relation: 1/chi = k + 6*pi*a*G*(omega)
    G_direct = ((1./chi_direct) - k_fit) ./ (6 * pi * a_um);  % Pa
    % k_from_chi = median(real(1./chi_direct(1:min(10,end))));
    % G_direct = ((1./chi_direct) - k_from_chi) ./ (6*pi*a_um);


    %% ---------- FIGURES ----------
    % Fig 1: PSD
    figure(100+gi); clf;
    loglog(f_exp, PSD_mean, 'k.', 'DisplayName', 'Raw PSD (Avg)'); hold on;
    loglog(f_exp, PSD_smooth, 'g-', 'LineWidth', 1.5, 'DisplayName', 'Smoothed PSD');
    y_fit_plot = ob_nmode_psd_model(f_exp, pfit, kT_um, Nmodes_OB);
    loglog(f_exp, y_fit_plot, 'r-', 'LineWidth', 2, 'DisplayName', 'OB Fit (on Smooth)');
    title(['PSD and Smoothing: P = ' num2str(P)]); xlabel('f (Hz)'); ylabel('PSD (\mum^2/Hz)');
    grid on; legend('Location','best');

    % Fig 2: Moduli
    figure(200+gi); clf;
    if plot_real_data
        loglog(omega, real(G_direct), 'r.', 'DisplayName', 'G'' (Direct)'); hold on;
        loglog(omega, imag(G_direct), 'b.', 'DisplayName', 'G'''' (Direct)');
    end
    
    % Implied Moduli from OB-fit
    G_p_fit = zeros(size(omega));
    G_pp_fit = omega * (gs_fit / (6*pi*a_um));
    for i = 1:Nmodes_OB
        Gi = gp_fits(i) / (6*pi*a_um*lam_fits(i));
        den = 1 + (omega*lam_fits(i)).^2;
        G_p_fit  = G_p_fit  + (Gi*(omega*lam_fits(i)).^2)./den;
        G_pp_fit = G_pp_fit + (Gi*(omega*lam_fits(i)))./den;
    end
    if plot_oldroyd_fit
        loglog(omega, G_p_fit, 'r-', 'DisplayName', 'G'' (OB Fit)'); hold on;
        loglog(omega, G_pp_fit, 'b-', 'DisplayName', 'G'''' (OB Fit)');
    end
    
    % SAOS reference
    Gp_saos = zeros(size(omega)); Gpp_saos = saos.mu_s * omega;
    for m = 1:numel(saos.lambdas)
        Gi_s = saos.mus(m)/saos.lambdas(m);
        den = 1 + (omega*saos.lambdas(m)).^2;
        Gp_saos = Gp_saos + (Gi_s*(omega*saos.lambdas(m)).^2)./den;
        Gpp_saos = Gpp_saos + (Gi_s*(omega*saos.lambdas(m)))./den;
    end
    loglog(omega, Gp_saos, 'k--', 'DisplayName', 'G'' (SAOS)');
    loglog(omega, Gpp_saos, 'k:', 'DisplayName', 'G'''' (SAOS)');
    title(['Moduli: P = ' num2str(P)]); xlabel('\omega (rad/s)'); ylabel('G'', G'''' (Pa)');
    grid on; legend('Location','best'); ylim([1e-3, 1e2]);
end
end

function PSD = ob_nmode_psd_model(f, p, kT, Nmodes)
    gs = p(1); gps = p(2:1+Nmodes); lams = p(2+Nmodes : 1+2*Nmodes); k = p(end);
    omega = 2 * pi * f;
    g_star = gs * ones(size(omega));
    for i = 1:Nmodes
        g_star = g_star + gps(i) ./ (1 + 1i * omega * lams(i));
    end
    chi = 1 ./ (k + 1i * omega .* g_star);
    PSD = (2 * kT ./ (omega + eps)) .* (-imag(chi));
end